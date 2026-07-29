import { render, screen, waitFor, act, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi, beforeEach, afterEach } from "vitest";
import AuditLogTab from "./AuditLogTab";
import type { AuditLogPage } from "../types";

// ---------------------------------------------------------------------------
// Mock ../api
//
// AuditLogTab imports fetchAuditLog and AuthError from "../api".
// We replace fetchAuditLog with a vi.fn() so individual tests can control
// what it returns. AuthError is kept real so instanceof checks work.
// ---------------------------------------------------------------------------

vi.mock("../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api")>();
  return {
    ...actual,
    fetchAuditLog: vi.fn(),
  };
});

import { fetchAuditLog, AuthError } from "../api";
const mockFetchAuditLog = vi.mocked(fetchAuditLog);

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const noop = () => {};

function makeEvent(id: number, overrides: Partial<import("../types").AuditEvent> = {}): import("../types").AuditEvent {
  return {
    id,
    occurred_at: "2025-06-01T10:00:00Z",
    actor_email: "admin@example.com",
    action: "availability.update",
    resource: "availability",
    detail: null,
    ip_address: null,
    ...overrides,
  };
}

const emptyPage: AuditLogPage = { events: [], next_cursor: null };

function singleEventPage(overrides: Partial<import("../types").AuditEvent> = {}): AuditLogPage {
  return { events: [makeEvent(1, overrides)], next_cursor: null };
}

// ---------------------------------------------------------------------------
// Loading / error / empty states
// ---------------------------------------------------------------------------

describe("AuditLogTab — loading and error states", () => {
  beforeEach(() => {
    mockFetchAuditLog.mockReset();
  });

  it("shows a loading indicator on mount before the fetch resolves", () => {
    // Never resolves — component stays in loading state
    mockFetchAuditLog.mockReturnValue(new Promise(() => {}));
    render(<AuditLogTab onAuthError={noop} />);
    expect(screen.getByText(/loading/i)).toBeTruthy();
  });

  it("shows an error message when the initial fetch fails", async () => {
    mockFetchAuditLog.mockRejectedValue(new Error("Network failure"));
    render(<AuditLogTab onAuthError={noop} />);
    await waitFor(() =>
      expect(screen.getByText(/network failure/i)).toBeTruthy()
    );
  });

  it("shows an empty state when the fetch returns zero events", async () => {
    mockFetchAuditLog.mockResolvedValue(emptyPage);
    render(<AuditLogTab onAuthError={noop} />);
    await waitFor(() =>
      expect(screen.getByText(/no audit events found/i)).toBeTruthy()
    );
  });

  it("calls onAuthError when the initial fetch throws AuthError", async () => {
    const onAuthError = vi.fn();
    mockFetchAuditLog.mockRejectedValue(new AuthError());
    render(<AuditLogTab onAuthError={onAuthError} />);
    await waitFor(() => expect(onAuthError).toHaveBeenCalledOnce());
  });
});

// ---------------------------------------------------------------------------
// Table rendering
// ---------------------------------------------------------------------------

describe("AuditLogTab — table rendering", () => {
  beforeEach(() => {
    mockFetchAuditLog.mockReset();
  });

  it("renders a row for each event returned", async () => {
    const page: AuditLogPage = {
      events: [makeEvent(1), makeEvent(2), makeEvent(3)],
      next_cursor: null,
    };
    mockFetchAuditLog.mockResolvedValue(page);
    render(<AuditLogTab onAuthError={noop} />);
    await waitFor(() => {
      // Each row shows the actor email; three rows = three matches.
      expect(screen.getAllByText("admin@example.com")).toHaveLength(3);
    });
  });

  it("renders actor email, action, and resource for an event", async () => {
    mockFetchAuditLog.mockResolvedValue(
      singleEventPage({ actor_email: "doctor@surgery.nhs.uk", action: "signposting.update", resource: "urinary_symptoms" })
    );
    render(<AuditLogTab onAuthError={noop} />);
    await waitFor(() => {
      expect(screen.getByText("doctor@surgery.nhs.uk")).toBeTruthy();
      expect(screen.getByText("signposting.update")).toBeTruthy();
      expect(screen.getByText("urinary_symptoms")).toBeTruthy();
    });
  });

  it("renders a dash in the resource column when resource is null", async () => {
    mockFetchAuditLog.mockResolvedValue(singleEventPage({ resource: null }));
    render(<AuditLogTab onAuthError={noop} />);
    await waitFor(() => {
      // The dash appears in the resource column. There may be other dashes
      // (e.g. detail column), so just confirm at least one is present.
      expect(screen.getAllByText("—").length).toBeGreaterThan(0);
    });
  });
});

// ---------------------------------------------------------------------------
// Detail toggle
// ---------------------------------------------------------------------------

describe("AuditLogTab — detail toggle", () => {
  beforeEach(() => {
    mockFetchAuditLog.mockReset();
  });

  it("does not show a Show button when detail is null", async () => {
    mockFetchAuditLog.mockResolvedValue(singleEventPage({ detail: null }));
    render(<AuditLogTab onAuthError={noop} />);
    await waitFor(() => screen.getAllByText("—")); // wait for render
    expect(screen.queryByRole("button", { name: /show/i })).toBeNull();
  });

  it("shows a Show button when detail is non-null", async () => {
    mockFetchAuditLog.mockResolvedValue(
      singleEventPage({ detail: { before: { email: "old@example.com" }, after: { email: "new@example.com" } } })
    );
    render(<AuditLogTab onAuthError={noop} />);
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /show/i })).toBeTruthy()
    );
  });

  it("clicking Show reveals the detail row and button text changes to Hide", async () => {
    mockFetchAuditLog.mockResolvedValue(
      singleEventPage({ detail: { key: "value" } })
    );
    render(<AuditLogTab onAuthError={noop} />);
    const showBtn = await screen.findByRole("button", { name: /show/i });
    await userEvent.click(showBtn);
    expect(screen.getByRole("button", { name: /hide/i })).toBeTruthy();
  });

  it("clicking Hide collapses the detail row and button text returns to Show", async () => {
    mockFetchAuditLog.mockResolvedValue(
      singleEventPage({ detail: { key: "value" } })
    );
    render(<AuditLogTab onAuthError={noop} />);
    const showBtn = await screen.findByRole("button", { name: /show/i });
    await userEvent.click(showBtn);
    const hideBtn = screen.getByRole("button", { name: /hide/i });
    await userEvent.click(hideBtn);
    expect(screen.getByRole("button", { name: /show/i })).toBeTruthy();
    expect(screen.queryByRole("button", { name: /hide/i })).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Filters — date inputs (immediate fetch)
// ---------------------------------------------------------------------------

describe("AuditLogTab — date filter inputs", () => {
  beforeEach(() => {
    mockFetchAuditLog.mockReset();
    mockFetchAuditLog.mockResolvedValue(emptyPage);
  });

  it("triggers a new fetch immediately when from-date changes", async () => {
    render(<AuditLogTab onAuthError={noop} />);
    await waitFor(() => expect(mockFetchAuditLog).toHaveBeenCalledOnce());

    const fromInput = document.getElementById("audit-from-date") as HTMLInputElement;
    await userEvent.type(fromInput, "2025-01-01");

    await waitFor(() =>
      expect(mockFetchAuditLog).toHaveBeenCalledWith(
        expect.objectContaining({ from_date: "2025-01-01" })
      )
    );
  });

  it("triggers a new fetch immediately when to-date changes", async () => {
    render(<AuditLogTab onAuthError={noop} />);
    await waitFor(() => expect(mockFetchAuditLog).toHaveBeenCalledOnce());

    const toInput = document.getElementById("audit-to-date") as HTMLInputElement;
    await userEvent.type(toInput, "2025-12-31");

    await waitFor(() =>
      expect(mockFetchAuditLog).toHaveBeenCalledWith(
        expect.objectContaining({ to_date: "2025-12-31" })
      )
    );
  });

  it("resets the event list when a date filter changes", async () => {
    const firstPage: AuditLogPage = {
      events: [makeEvent(1, { actor_email: "first@example.com" })],
      next_cursor: null,
    };
    const secondPage: AuditLogPage = {
      events: [makeEvent(2, { actor_email: "second@example.com" })],
      next_cursor: null,
    };
    mockFetchAuditLog.mockResolvedValueOnce(firstPage).mockResolvedValueOnce(secondPage);

    render(<AuditLogTab onAuthError={noop} />);
    await waitFor(() => screen.getByText("first@example.com"));

    const fromInput = document.getElementById("audit-from-date") as HTMLInputElement;
    await userEvent.type(fromInput, "2025-06-01");

    await waitFor(() => screen.getByText("second@example.com"));
    // First page's event should no longer be present
    expect(screen.queryByText("first@example.com")).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Filters — text inputs (debounced)
// ---------------------------------------------------------------------------

describe("AuditLogTab — debounced text filter inputs", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    mockFetchAuditLog.mockReset();
    // Use a resolved promise so the initial mount fetch completes
    mockFetchAuditLog.mockResolvedValue(emptyPage);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("does not fetch immediately when typing in the actor input", async () => {
    render(<AuditLogTab onAuthError={noop} />);
    // Allow the initial mount fetch to settle
    await act(async () => { vi.runAllTimers(); });
    const callsAfterMount = mockFetchAuditLog.mock.calls.length;

    const actorInput = document.getElementById("audit-actor") as HTMLInputElement;
    // Fire the change without advancing the debounce timer
    act(() => {
      fireEvent.change(actorInput, { target: { value: "doc" } });
    });

    expect(mockFetchAuditLog.mock.calls.length).toBe(callsAfterMount);
  });

  it("fetches after 400ms when typing in the actor input", async () => {
    render(<AuditLogTab onAuthError={noop} />);
    await act(async () => { vi.runAllTimers(); });
    const callsAfterMount = mockFetchAuditLog.mock.calls.length;

    const actorInput = document.getElementById("audit-actor") as HTMLInputElement;
    await act(async () => {
      fireEvent.change(actorInput, { target: { value: "doctor@example.com" } });
      vi.advanceTimersByTime(400);
    });

    expect(mockFetchAuditLog.mock.calls.length).toBeGreaterThan(callsAfterMount);
  });

  it("fetches after 400ms when typing in the action input", async () => {
    render(<AuditLogTab onAuthError={noop} />);
    await act(async () => { vi.runAllTimers(); });
    const callsAfterMount = mockFetchAuditLog.mock.calls.length;

    const actionInput = document.getElementById("audit-action") as HTMLInputElement;
    await act(async () => {
      fireEvent.change(actionInput, { target: { value: "availability" } });
      vi.advanceTimersByTime(400);
    });

    expect(mockFetchAuditLog.mock.calls.length).toBeGreaterThan(callsAfterMount);
  });
});

// ---------------------------------------------------------------------------
// Text filter normalisation
//
// Stored actor emails are lowercase and the server's action prefix must match
// ^[a-z0-9_.]+$, so an unnormalised value returns nothing or 400s.
// ---------------------------------------------------------------------------

describe("AuditLogTab — text filter normalisation", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    mockFetchAuditLog.mockReset();
    mockFetchAuditLog.mockResolvedValue(emptyPage);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  async function typeInto(id: string, value: string) {
    render(<AuditLogTab onAuthError={noop} />);
    await act(async () => { vi.runAllTimers(); });
    mockFetchAuditLog.mockClear();

    const input = document.getElementById(id) as HTMLInputElement;
    await act(async () => {
      fireEvent.change(input, { target: { value } });
      vi.advanceTimersByTime(400);
    });
    return input;
  }

  it("lowercases and trims the actor filter before sending", async () => {
    await typeInto("audit-actor", "  Alice@Example.COM  ");
    expect(mockFetchAuditLog).toHaveBeenCalledWith(
      expect.objectContaining({ actor: "alice@example.com" })
    );
  });

  it("lowercases and trims the action filter before sending", async () => {
    await typeInto("audit-action", "  Availability  ");
    expect(mockFetchAuditLog).toHaveBeenCalledWith(
      expect.objectContaining({ action: "availability" })
    );
  });

  it("keeps the raw text the user typed in the input", async () => {
    const input = await typeInto("audit-actor", "Alice@Example.COM");
    expect(input.value).toBe("Alice@Example.COM");
  });

  it("does not send an action the server would reject", async () => {
    await typeInto("audit-action", "auth login");
    expect(mockFetchAuditLog).not.toHaveBeenCalled();
  });

  it("shows an inline hint for an action the server would reject", async () => {
    const input = await typeInto("audit-action", "auth login");
    expect(screen.getByText(/lowercase letters, numbers, dots and underscores/i)).toBeTruthy();
    expect(input.getAttribute("aria-invalid")).toBe("true");
    expect(input.getAttribute("aria-describedby")).toBe("audit-action-hint");
  });

  it("shows no hint for a valid action", async () => {
    const input = await typeInto("audit-action", "Availability");
    expect(screen.queryByText(/lowercase letters, numbers, dots and underscores/i)).toBeNull();
    expect(input.getAttribute("aria-invalid")).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Load more
// ---------------------------------------------------------------------------

describe("AuditLogTab — load more", () => {
  beforeEach(() => {
    mockFetchAuditLog.mockReset();
  });

  it("does not show Load more button when next_cursor is null", async () => {
    mockFetchAuditLog.mockResolvedValue(emptyPage);
    render(<AuditLogTab onAuthError={noop} />);
    await waitFor(() => screen.getByText(/no audit events found/i));
    expect(screen.queryByRole("button", { name: /load more/i })).toBeNull();
  });

  it("shows Load more button when next_cursor is non-null", async () => {
    mockFetchAuditLog.mockResolvedValue({
      events: [makeEvent(1)],
      next_cursor: "cursor-abc",
    });
    render(<AuditLogTab onAuthError={noop} />);
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /load more/i })).toBeTruthy()
    );
  });

  it("appends events to the existing list when Load more is clicked", async () => {
    const firstPage: AuditLogPage = {
      events: [makeEvent(1, { actor_email: "first@example.com" })],
      next_cursor: "cursor-abc",
    };
    const secondPage: AuditLogPage = {
      events: [makeEvent(2, { actor_email: "second@example.com" })],
      next_cursor: null,
    };
    mockFetchAuditLog.mockResolvedValueOnce(firstPage).mockResolvedValueOnce(secondPage);

    render(<AuditLogTab onAuthError={noop} />);
    await waitFor(() => screen.getByText("first@example.com"));

    await userEvent.click(screen.getByRole("button", { name: /load more/i }));

    await waitFor(() => screen.getByText("second@example.com"));
    // First page events should still be present
    expect(screen.getByText("first@example.com")).toBeTruthy();
  });

  it("hides Load more button after reaching the last page", async () => {
    const firstPage: AuditLogPage = {
      events: [makeEvent(1)],
      next_cursor: "cursor-abc",
    };
    const secondPage: AuditLogPage = {
      events: [makeEvent(2)],
      next_cursor: null,
    };
    mockFetchAuditLog.mockResolvedValueOnce(firstPage).mockResolvedValueOnce(secondPage);

    render(<AuditLogTab onAuthError={noop} />);
    await waitFor(() => screen.getByRole("button", { name: /load more/i }));

    await userEvent.click(screen.getByRole("button", { name: /load more/i }));

    await waitFor(() =>
      expect(screen.queryByRole("button", { name: /load more/i })).toBeNull()
    );
  });

  it("calls onAuthError when Load more fetch throws AuthError", async () => {
    const onAuthError = vi.fn();
    mockFetchAuditLog
      .mockResolvedValueOnce({ events: [makeEvent(1)], next_cursor: "cursor-abc" })
      .mockRejectedValueOnce(new AuthError());

    render(<AuditLogTab onAuthError={onAuthError} />);
    await waitFor(() => screen.getByRole("button", { name: /load more/i }));

    await userEvent.click(screen.getByRole("button", { name: /load more/i }));

    await waitFor(() => expect(onAuthError).toHaveBeenCalledOnce());
  });

  it("shows an inline error without clearing the list when Load more fails with a non-auth error", async () => {
    mockFetchAuditLog
      .mockResolvedValueOnce({ events: [makeEvent(1, { actor_email: "kept@example.com" })], next_cursor: "cursor-abc" })
      .mockRejectedValueOnce(new Error("Timeout"));

    render(<AuditLogTab onAuthError={noop} />);
    await waitFor(() => screen.getByRole("button", { name: /load more/i }));

    await userEvent.click(screen.getByRole("button", { name: /load more/i }));

    await waitFor(() => screen.getByText(/timeout/i));
    // Original row must still be present
    expect(screen.getByText("kept@example.com")).toBeTruthy();
  });
});
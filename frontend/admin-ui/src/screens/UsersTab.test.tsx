import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi, beforeEach } from "vitest";
import UsersTab from "./UsersTab";
import type { AdminUser } from "../types";

// ---------------------------------------------------------------------------
// Mock ../api
//
// UsersTab imports fetchUsers, addUser, removeUser, resendInvitation, and
// AuthError from "../api". We replace the four async functions with vi.fn()
// so individual tests can control their return values. AuthError is kept real
// so instanceof checks inside UsersTab work correctly.
// ---------------------------------------------------------------------------

vi.mock("../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api")>();
  return {
    ...actual,
    fetchUsers: vi.fn(),
    addUser: vi.fn(),
    removeUser: vi.fn(),
    resendInvitation: vi.fn(),
  };
});

import { fetchUsers, addUser, removeUser, resendInvitation, AuthError } from "../api";
const mockFetchUsers = vi.mocked(fetchUsers);
const mockAddUser = vi.mocked(addUser);
const mockRemoveUser = vi.mocked(removeUser);
const mockResendInvitation = vi.mocked(resendInvitation);

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const noop = () => {};

function makeUser(overrides: Partial<AdminUser> = {}): AdminUser {
  return {
    id: "user-1",
    email: "admin@example.com",
    is_current_user: false,
    last_login: "2025-06-01T10:00:00Z",
    created_at: "2025-01-01T00:00:00Z",
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Loading / error / empty states
// ---------------------------------------------------------------------------

describe("UsersTab — loading and error states", () => {
  beforeEach(() => {
    mockFetchUsers.mockReset();
  });

  it("shows a loading indicator on mount before the fetch resolves", () => {
    mockFetchUsers.mockReturnValue(new Promise(() => {}));
    render(<UsersTab onAuthError={noop} />);
    expect(screen.getByText(/loading/i)).toBeTruthy();
  });

  it("shows an error message when the initial fetch fails", async () => {
    mockFetchUsers.mockRejectedValue(new Error("Network failure"));
    render(<UsersTab onAuthError={noop} />);
    await waitFor(() =>
      expect(screen.getByText(/failed to load users/i)).toBeTruthy()
    );
  });

  it("shows an empty state when the fetch returns zero users", async () => {
    mockFetchUsers.mockResolvedValue([]);
    render(<UsersTab onAuthError={noop} />);
    await waitFor(() =>
      expect(screen.getByText(/no admin users found/i)).toBeTruthy()
    );
  });

  it("calls onAuthError when the initial fetch throws AuthError", async () => {
    const onAuthError = vi.fn();
    mockFetchUsers.mockRejectedValue(new AuthError());
    render(<UsersTab onAuthError={onAuthError} />);
    await waitFor(() => expect(onAuthError).toHaveBeenCalledOnce());
  });
});

// ---------------------------------------------------------------------------
// User list rendering
// ---------------------------------------------------------------------------

describe("UsersTab — user list rendering", () => {
  beforeEach(() => {
    mockFetchUsers.mockReset();
  });

  it("renders a row for each returned user", async () => {
    mockFetchUsers.mockResolvedValue([
      makeUser({ id: "user-1", email: "alice@example.com" }),
      makeUser({ id: "user-2", email: "bob@example.com" }),
    ]);
    render(<UsersTab onAuthError={noop} />);
    await waitFor(() => {
      expect(screen.getByText("alice@example.com")).toBeTruthy();
      expect(screen.getByText("bob@example.com")).toBeTruthy();
    });
  });

  it("labels the current user with a 'You' badge", async () => {
    mockFetchUsers.mockResolvedValue([
      makeUser({ id: "user-1", email: "me@example.com", is_current_user: true }),
    ]);
    render(<UsersTab onAuthError={noop} />);
    await waitFor(() =>
      expect(screen.getByText("You")).toBeTruthy()
    );
  });

  it("does not show a 'You' badge for other users", async () => {
    mockFetchUsers.mockResolvedValue([
      makeUser({ id: "user-1", email: "other@example.com", is_current_user: false }),
    ]);
    render(<UsersTab onAuthError={noop} />);
    await waitFor(() => screen.getByText("other@example.com"));
    expect(screen.queryByText("You")).toBeNull();
  });

  it("shows 'Pending' for a user with no last_login", async () => {
    mockFetchUsers.mockResolvedValue([
      makeUser({ last_login: null }),
    ]);
    render(<UsersTab onAuthError={noop} />);
    await waitFor(() =>
      expect(screen.getByText(/pending/i)).toBeTruthy()
    );
  });

  it("does not show a 'Pending' label when the user has logged in", async () => {
    mockFetchUsers.mockResolvedValue([
      makeUser({ last_login: "2025-06-01T10:00:00Z" }),
    ]);
    render(<UsersTab onAuthError={noop} />);
    await waitFor(() => screen.getByText("admin@example.com"));
    expect(screen.queryByText(/pending/i)).toBeNull();
  });

  it("shows 'Resend Invite' only for users with no last_login", async () => {
    mockFetchUsers.mockResolvedValue([
      makeUser({ id: "user-1", email: "pending@example.com", last_login: null }),
      makeUser({ id: "user-2", email: "active@example.com", last_login: "2025-06-01T10:00:00Z" }),
    ]);
    render(<UsersTab onAuthError={noop} />);
    await waitFor(() => screen.getByText("pending@example.com"));
    expect(screen.getAllByRole("button", { name: /resend invite/i })).toHaveLength(1);
  });
});

// ---------------------------------------------------------------------------
// Remove button guards
// ---------------------------------------------------------------------------

describe("UsersTab — Remove button guards", () => {
  beforeEach(() => {
    mockFetchUsers.mockReset();
  });

  it("disables the Remove button for the current user", async () => {
    mockFetchUsers.mockResolvedValue([
      makeUser({ id: "user-1", is_current_user: true }),
    ]);
    render(<UsersTab onAuthError={noop} />);
    const btn = await screen.findByRole("button", { name: /^remove$/i });
    expect((btn as HTMLButtonElement).disabled).toBe(true);
  });

  it("enables the Remove button for other users", async () => {
    mockFetchUsers.mockResolvedValue([
      makeUser({ id: "user-1", is_current_user: false }),
    ]);
    render(<UsersTab onAuthError={noop} />);
    const btn = await screen.findByRole("button", { name: /^remove$/i });
    expect((btn as HTMLButtonElement).disabled).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// Add user
// ---------------------------------------------------------------------------

describe("UsersTab — add user", () => {
  beforeEach(() => {
    mockFetchUsers.mockReset();
    mockAddUser.mockReset();
    // Provide a stable return for the re-fetch that follows a successful add.
    mockFetchUsers.mockResolvedValue([]);
  });

  it("disables the Add Admin button when the email input is empty", async () => {
    mockFetchUsers.mockResolvedValue([]);
    render(<UsersTab onAuthError={noop} />);
    await waitFor(() => screen.getByText(/no admin users found/i));
    const btn = screen.getByRole("button", { name: /add admin/i });
    expect((btn as HTMLButtonElement).disabled).toBe(true);
  });

  it("re-fetches the user list on successful add", async () => {
    mockAddUser.mockResolvedValue({ ok: true, email_sent: true });
    render(<UsersTab onAuthError={noop} />);
    await waitFor(() => screen.getByLabelText(/email address/i));

    await userEvent.type(screen.getByLabelText(/email address/i), "new@example.com");
    await userEvent.click(screen.getByRole("button", { name: /add admin/i }));

    await waitFor(() => expect(mockFetchUsers).toHaveBeenCalledTimes(2));
  });

  it("clears the email input after a successful add", async () => {
    mockAddUser.mockResolvedValue({ ok: true, email_sent: true });
    render(<UsersTab onAuthError={noop} />);
    await waitFor(() => screen.getByLabelText(/email address/i));

    const input = screen.getByLabelText(/email address/i) as HTMLInputElement;
    await userEvent.type(input, "new@example.com");
    await userEvent.click(screen.getByRole("button", { name: /add admin/i }));

    await waitFor(() => expect(input.value).toBe(""));
  });

  it("shows a warning when add succeeds but email_sent is false", async () => {
    mockAddUser.mockResolvedValue({ ok: true, email_sent: false });
    render(<UsersTab onAuthError={noop} />);
    await waitFor(() => screen.getByLabelText(/email address/i));

    await userEvent.type(screen.getByLabelText(/email address/i), "new@example.com");
    await userEvent.click(screen.getByRole("button", { name: /add admin/i }));

    await waitFor(() =>
      expect(screen.getByText(/invitation email failed to send/i)).toBeTruthy()
    );
  });

  it("shows an inline error message when addUser throws", async () => {
    mockAddUser.mockRejectedValue(new Error("A user with this email already exists."));
    render(<UsersTab onAuthError={noop} />);
    await waitFor(() => screen.getByLabelText(/email address/i));

    await userEvent.type(screen.getByLabelText(/email address/i), "dupe@example.com");
    await userEvent.click(screen.getByRole("button", { name: /add admin/i }));

    await waitFor(() =>
      expect(screen.getByText(/a user with this email already exists/i)).toBeTruthy()
    );
  });

  it("calls onAuthError when addUser throws AuthError", async () => {
    const onAuthError = vi.fn();
    mockAddUser.mockRejectedValue(new AuthError());
    render(<UsersTab onAuthError={onAuthError} />);
    await waitFor(() => screen.getByLabelText(/email address/i));

    await userEvent.type(screen.getByLabelText(/email address/i), "any@example.com");
    await userEvent.click(screen.getByRole("button", { name: /add admin/i }));

    await waitFor(() => expect(onAuthError).toHaveBeenCalledOnce());
  });
});

// ---------------------------------------------------------------------------
// Remove user
// ---------------------------------------------------------------------------

describe("UsersTab — remove user", () => {
  beforeEach(() => {
    mockFetchUsers.mockReset();
    mockRemoveUser.mockReset();
  });

  it("re-fetches the user list after a successful removal", async () => {
    mockFetchUsers.mockResolvedValue([
      makeUser({ id: "user-1", is_current_user: false }),
    ]);
    mockRemoveUser.mockResolvedValue(undefined);

    render(<UsersTab onAuthError={noop} />);
    const btn = await screen.findByRole("button", { name: /^remove$/i });
    await userEvent.click(btn);

    await waitFor(() => expect(mockFetchUsers).toHaveBeenCalledTimes(2));
  });

  it("shows an inline error when removeUser throws", async () => {
    mockFetchUsers.mockResolvedValue([
      makeUser({ id: "user-1", is_current_user: false }),
    ]);
    mockRemoveUser.mockRejectedValue(new Error("You cannot delete the last admin user."));

    render(<UsersTab onAuthError={noop} />);
    const btn = await screen.findByRole("button", { name: /^remove$/i });
    await userEvent.click(btn);

    await waitFor(() =>
      expect(screen.getByText(/you cannot delete the last admin user/i)).toBeTruthy()
    );
  });

  it("calls onAuthError when removeUser throws AuthError", async () => {
    const onAuthError = vi.fn();
    mockFetchUsers.mockResolvedValue([
      makeUser({ id: "user-1", is_current_user: false }),
    ]);
    mockRemoveUser.mockRejectedValue(new AuthError());

    render(<UsersTab onAuthError={onAuthError} />);
    const btn = await screen.findByRole("button", { name: /^remove$/i });
    await userEvent.click(btn);

    await waitFor(() => expect(onAuthError).toHaveBeenCalledOnce());
  });
});

// ---------------------------------------------------------------------------
// Resend invitation
// ---------------------------------------------------------------------------

describe("UsersTab — resend invitation", () => {
  beforeEach(() => {
    mockFetchUsers.mockReset();
    mockResendInvitation.mockReset();
  });

  it("shows a success message when resend succeeds with email_sent true", async () => {
    mockFetchUsers.mockResolvedValue([
      makeUser({ id: "user-1", last_login: null }),
    ]);
    mockResendInvitation.mockResolvedValue({ ok: true, email_sent: true });

    render(<UsersTab onAuthError={noop} />);
    const btn = await screen.findByRole("button", { name: /resend invite/i });
    await userEvent.click(btn);

    await waitFor(() =>
      expect(screen.getByText(/invitation email sent/i)).toBeTruthy()
    );
  });

  it("shows a warning when resend succeeds but email_sent is false", async () => {
    mockFetchUsers.mockResolvedValue([
      makeUser({ id: "user-1", last_login: null }),
    ]);
    mockResendInvitation.mockResolvedValue({ ok: true, email_sent: false });

    render(<UsersTab onAuthError={noop} />);
    const btn = await screen.findByRole("button", { name: /resend invite/i });
    await userEvent.click(btn);

    await waitFor(() =>
      expect(screen.getByText(/invitation email failed to send/i)).toBeTruthy()
    );
  });

  it("shows an inline error when resendInvitation throws", async () => {
    mockFetchUsers.mockResolvedValue([
      makeUser({ id: "user-1", last_login: null }),
    ]);
    mockResendInvitation.mockRejectedValue(new Error("User not found."));

    render(<UsersTab onAuthError={noop} />);
    const btn = await screen.findByRole("button", { name: /resend invite/i });
    await userEvent.click(btn);

    await waitFor(() =>
      expect(screen.getByText(/user not found/i)).toBeTruthy()
    );
  });

  it("calls onAuthError when resendInvitation throws AuthError", async () => {
    const onAuthError = vi.fn();
    mockFetchUsers.mockResolvedValue([
      makeUser({ id: "user-1", last_login: null }),
    ]);
    mockResendInvitation.mockRejectedValue(new AuthError());

    render(<UsersTab onAuthError={onAuthError} />);
    const btn = await screen.findByRole("button", { name: /resend invite/i });
    await userEvent.click(btn);

    await waitFor(() => expect(onAuthError).toHaveBeenCalledOnce());
  });
});
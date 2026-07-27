/**
 * App.test.tsx
 *
 * Tests for the root component's session-expiry overlay behaviour.
 *
 * Mocking strategy: EditorView and LoginView are replaced with stubs that
 * expose their props (onAuthError / onSuccess) as test hooks, and the api
 * module is mocked so no real HTTP calls are made. This isolates the tests
 * to App's own state transitions.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import App from "./App";
import type { ConditionSummary } from "./types";

const twoConditions: ConditionSummary[] = [
  { id: "urinary_symptoms", label: "Urinary symptoms" },
];

vi.mock("./api", () => ({
  fetchConditions: vi.fn(),
  logout: vi.fn(),
  AuthError: class AuthError extends Error {},
}));

import { fetchConditions, logout } from "./api";

const mockFetchConditions = vi.mocked(fetchConditions);
const mockLogout = vi.mocked(logout);

let triggerAuthError: () => void = () => {};

vi.mock("./screens/EditorView", () => ({
  default: ({ onAuthError }: { onAuthError: () => void }) => {
    triggerAuthError = onAuthError;
    return <div data-testid="editor-view" />;
  },
}));

let triggerReloginSuccess: () => void = () => {};

vi.mock("./screens/LoginView", () => ({
  default: ({ onSuccess }: { onSuccess: () => void }) => {
    triggerReloginSuccess = onSuccess;
    return <div data-testid="login-view" />;
  },
}));

beforeEach(() => {
  mockFetchConditions.mockReset();
  mockLogout.mockReset();
  mockLogout.mockResolvedValue(undefined);
});

async function renderInEditor() {
  mockFetchConditions.mockResolvedValue(twoConditions);
  render(<App />);
  await waitFor(() => expect(screen.getByTestId("editor-view")).toBeTruthy());
}

describe("App — mid-session expiry overlay", () => {
  it("does not show the overlay initially", async () => {
    await renderInEditor();
    expect(screen.queryByTestId("login-view")).toBeNull();
  });

  it("shows a login overlay with the editor still mounted when onAuthError fires", async () => {
    await renderInEditor();
    triggerAuthError();
    await waitFor(() => expect(screen.getByTestId("login-view")).toBeTruthy());
    expect(screen.getByTestId("editor-view")).toBeTruthy();
  });

  it("dismisses the overlay on successful re-login without unmounting the editor", async () => {
    await renderInEditor();
    triggerAuthError();
    await waitFor(() => expect(screen.getByTestId("login-view")).toBeTruthy());

    triggerReloginSuccess();
    await waitFor(() => expect(screen.queryByTestId("login-view")).toBeNull());
    expect(screen.getByTestId("editor-view")).toBeTruthy();
    expect(mockFetchConditions).toHaveBeenCalledTimes(1);
  });

  it("discards state and shows full-page login when 'Log out and discard changes' is clicked", async () => {
    await renderInEditor();
    triggerAuthError();
    await waitFor(() => expect(screen.getByTestId("login-view")).toBeTruthy());

    await userEvent.click(
      screen.getByRole("button", { name: "Log out and discard changes" })
    );

    await waitFor(() => expect(mockLogout).toHaveBeenCalledOnce());
    expect(screen.queryByTestId("editor-view")).toBeNull();
    // Full-page LoginView is now shown (not the overlay's own stub instance count matters less
    // than the editor being gone).
    expect(screen.getByTestId("login-view")).toBeTruthy();
  });
});

/**
 * App.tsx — admin portal root component.
 *
 * Authentication is cookie-based. On mount, App checks window.location.hash
 * before probing the session:
 *
 * - If the hash matches #reset:{token}, bypass the session probe and go
 *   directly to set_password state. SetPasswordView extracts and clears
 *   the hash on its own mount.
 *
 * - Otherwise, attempt to fetch the condition list. If it succeeds, the
 *   session cookie is valid and EditorView is shown immediately. If it
 *   returns 401 (AuthError), LoginView is shown instead.
 *
 * Session expiry mid-session (sliding 60-minute TTL): any AuthError thrown
 * by an EditorView API call propagates to handleAuthError, which sets
 * sessionExpired instead of leaving the editor state. EditorView stays
 * mounted underneath — SignpostingEditor/AvailabilityEditor state, the
 * active tab, and the selected condition all survive — while LoginView is
 * shown in a modal overlay on top. On successful re-login, the overlay is
 * dismissed with no refetch and no remount; the user re-clicks whatever
 * action failed. The explicit "Log out and discard changes" escape hatch
 * and the full-page logout path both discard state, same as before.
 */

import { useState, useEffect } from "react";
import LoginView from "./screens/LoginView";
import SetPasswordView from "./screens/SetPasswordView";
import EditorView from "./screens/EditorView";
import type { ConditionSummary } from "./types";
import { fetchConditions, AuthError, logout } from "./api";

type AuthState = "checking" | "login" | "editor" | "set_password";

export default function App() {
  const [authState, setAuthState] = useState<AuthState>("checking");
  const [conditions, setConditions] = useState<ConditionSummary[]>([]);
  const [sessionExpired, setSessionExpired] = useState(false);

  useEffect(() => {
    // Check for a password reset/setup hash before probing the session.
    // This prevents an unnecessary authenticated API call when the user
    // has arrived via a setup link.
    if (/^#reset:/.test(window.location.hash)) {
      setAuthState("set_password");
      return;
    }

    // Probe the session by fetching conditions.
    // Success -> go straight to editor. AuthError -> show login.
    fetchConditions()
      .then((loaded) => {
        setConditions(loaded);
        setAuthState("editor");
      })
      .catch((err) => {
        if (!(err instanceof AuthError)) {
          console.error("Startup fetch failed:", err);
        }
        setAuthState("login");
      });
  }, []);

  // Called by LoginView after successful MFA verification.
  async function handleLoginSuccess() {
    try {
      const loaded = await fetchConditions();
      setConditions(loaded);
      setAuthState("editor");
    } catch (err) {
      console.error("Post-login conditions fetch failed:", err);
      setAuthState("login");
    }
  }

  // Called by SetPasswordView when the user has set their password and
  // clicks "Go to login", or when the link was invalid.
  function handleSetPasswordComplete() {
    setAuthState("login");
  }

  // Called by EditorView when any API call returns 401 mid-session.
  // EditorView stays mounted; a login overlay is shown above it so
  // unsaved work survives re-authentication.
  function handleAuthError() {
    setSessionExpired(true);
  }

  // Called by the overlay LoginView after successful re-authentication.
  function handleReloginSuccess() {
    setSessionExpired(false);
  }

  // Called when the user clicks the explicit "Log out" button.
  async function handleLogout() {
    await logout();
    setConditions([]);
    setAuthState("login");
  }

  // Called from the overlay's "Log out and discard changes" escape hatch.
  async function handleDiscardAndLogout() {
    await logout();
    setConditions([]);
    setSessionExpired(false);
    setAuthState("login");
  }

  return (
    <div>
      <header className="page-header" style={{ display: "flex", alignItems: "center" }}>
        <span className="wordmark">econsult</span>
        <span className="separator" />
        <span className="title">Practice admin</span>

        {authState === "editor" && (
          <button
            className="tab-btn"
            onClick={handleLogout}
            style={{ marginLeft: "auto", cursor: "pointer" }}
          >
            Log out
          </button>
        )}
      </header>

      <main className="main">
        {authState === "checking" && (
          <div className="loading-row" style={{ marginTop: 48 }}>
            <span className="spinner dark" />
            Loading…
          </div>
        )}

        {authState === "login" && (
          <LoginView onSuccess={handleLoginSuccess} />
        )}

        {authState === "set_password" && (
          <SetPasswordView onComplete={handleSetPasswordComplete} />
        )}

        {authState === "editor" && (
          <EditorView
            conditions={conditions}
            onAuthError={handleAuthError}
          />
        )}
      </main>

      {sessionExpired && (
        <div className="modal-overlay">
          <div className="modal-panel">
            <p className="card-subtitle" style={{ marginBottom: 20 }}>
              Your session expired. Log in again to continue — your unsaved
              changes are kept.
            </p>
            <LoginView onSuccess={handleReloginSuccess} />
            <button
              className="btn btn-ghost"
              onClick={handleDiscardAndLogout}
              style={{ marginTop: 12 }}
            >
              Log out and discard changes
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
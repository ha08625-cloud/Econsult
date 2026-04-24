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
 * Session expiry mid-session: any AuthError thrown by an EditorView API
 * call propagates to handleAuthError, which transitions back to LoginView.
 * Any unsaved data in EditorView is lost — this is intentional given the
 * 24-hour session TTL and infrequent use pattern. See arch_admin.md.
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

  // Called by EditorView when any API call returns 401.
  function handleAuthError() {
    setConditions([]);
    setAuthState("login");
  }

  // Called when the user clicks the explicit "Log out" button.
  async function handleLogout() {
    await logout();
    setConditions([]);
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
    </div>
  );
}
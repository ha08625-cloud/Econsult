/**
 * App.tsx — admin portal root component.
 *
 * Authentication is cookie-based. On mount, App attempts to fetch the
 * condition list. If it succeeds, the session cookie is valid and
 * EditorView is shown immediately. If it returns 401 (AuthError),
 * LoginView is shown instead.
 *
 * Session expiry mid-session: any AuthError thrown by an EditorView API
 * call propagates to handleAuthError, which transitions back to LoginView.
 * Any unsaved data in EditorView is lost — this is intentional given the
 * 24-hour session TTL and infrequent use pattern. See arch_admin.md.
 *
 * TokenView has been removed. There is no token state.
 */

import { useState, useEffect } from "react";
import LoginView from "./LoginView";
import EditorView from "./EditorView";
import type { ConditionSummary } from "./types";
import { fetchConditions, AuthError } from "./api";

type AuthState = "checking" | "login" | "editor";

export default function App() {
  const [authState, setAuthState] = useState<AuthState>("checking");
  const [conditions, setConditions] = useState<ConditionSummary[]>([]);

  // On mount: probe the session by fetching conditions.
  // Success -> go straight to editor. AuthError -> show login.
  useEffect(() => {
    fetchConditions()
      .then((loaded) => {
        setConditions(loaded);
        setAuthState("editor");
      })
      .catch((err) => {
        // AuthError means no valid session — show login.
        // Any other error (network failure, 500) also shows login
        // since we cannot operate without conditions.
        if (!(err instanceof AuthError)) {
          console.error("Startup fetch failed:", err);
        }
        setAuthState("login");
      });
  }, []);

  // Called by LoginView after successful MFA verification.
  // Re-fetches conditions (session cookie is now set) then transitions
  // to EditorView.
  async function handleLoginSuccess() {
    try {
      const loaded = await fetchConditions();
      setConditions(loaded);
      setAuthState("editor");
    } catch (err) {
      // Should not happen immediately after successful verify, but guard
      // against it by staying on the login view.
      console.error("Post-login conditions fetch failed:", err);
      setAuthState("login");
    }
  }

  // Called by EditorView when any API call returns 401.
  // Transitions back to login — unsaved data is lost.
  function handleAuthError() {
    setConditions([]);
    setAuthState("login");
  }

  return (
    <div>
      <header className="page-header">
        <span className="wordmark">econsult</span>
        <span className="separator" />
        <span className="title">Practice admin</span>
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
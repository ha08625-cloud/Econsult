/**
 * SetPasswordView.tsx — password setup/reset screen.
 *
 * Rendered by App.tsx when window.location.hash matches #reset:{token}.
 *
 * On mount:
 * 1. Extract the raw token from the URL hash.
 * 2. Clear the hash immediately via history.replaceState to prevent the
 *    token from persisting in browser history and to avoid re-triggering
 *    the set_password flow on any subsequent navigation.
 * 3. If no token is found, show an error.
 *
 * UI:
 * - "New password" input with a zxcvbn-powered strength meter and
 *   actionable suggestions.
 * - "Confirm password" input.
 * - Submit button disabled until: password >= 12 chars, zxcvbn score >= 3,
 *   and the two fields match.
 *
 * On success: shows a confirmation message with a button to return to login.
 * On INVALID_RESET_TOKEN: shows a specific expired-link message.
 * On WEAK_PASSWORD: shows the zxcvbn feedback message from the server
 *   (should not normally fire since the client enforces the same rules,
 *   but guards against direct API calls or client-side bypasses).
 */

import { useState, useEffect } from "react";
import { zxcvbn, zxcvbnOptions } from "@zxcvbn-ts/core";
import * as zxcvbnCommonPackage from "@zxcvbn-ts/language-common";
import * as zxcvbnEnPackage from "@zxcvbn-ts/language-en";
import { setPassword } from "../api";

// Initialise zxcvbn with English language pack once at module load.
zxcvbnOptions.setOptions({
  translations: zxcvbnEnPackage.translations,
  graphs: zxcvbnCommonPackage.adjacencyGraphs,
  dictionary: {
    ...zxcvbnCommonPackage.dictionary,
    ...zxcvbnEnPackage.dictionary,
  },
});

interface Props {
  onComplete: () => void;
}

const MIN_LENGTH = 12;
const MIN_SCORE = 3;

// Strength meter colours indexed by zxcvbn score (0–4).
const SCORE_COLORS: Record<number, string> = {
  0: "#e53e3e",
  1: "#e53e3e",
  2: "#d69e2e",
  3: "#38a169",
  4: "#276749",
};

const SCORE_LABELS: Record<number, string> = {
  0: "Very weak",
  1: "Weak",
  2: "Fair",
  3: "Good",
  4: "Strong",
};

export default function SetPasswordView({ onComplete }: Props) {
  const [token, setToken] = useState<string | null>(null);
  const [password, setPasswordValue] = useState("");
  const [confirm, setConfirm] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  // Derived state — recalculated on every render, not stored in state.
  const result = password ? zxcvbn(password) : null;
  const score = result?.score ?? 0;
  const suggestions: string[] = result?.feedback?.suggestions ?? [];
  const warning: string = result?.feedback?.warning ?? "";

  const passwordLongEnough = password.length >= MIN_LENGTH;
  const passwordStrongEnough = score >= MIN_SCORE;
  const passwordsMatch = password === confirm && confirm.length > 0;
  const canSubmit =
    !isSubmitting &&
    passwordLongEnough &&
    passwordStrongEnough &&
    passwordsMatch;

  // On mount: extract and clear the URL hash token.
  useEffect(() => {
    const match = window.location.hash.match(/^#reset:(.+)$/);
    const extracted = match ? match[1] : null;

    // Clear the hash unconditionally — success, error, or no token.
    history.replaceState(null, "", location.pathname);

    if (extracted) {
      setToken(extracted);
    } else {
      setError(
        "Invalid or missing setup link. Please request a new one from the login page."
      );
    }
  }, []);

  async function handleSubmit() {
    if (!canSubmit || !token) return;

    setIsSubmitting(true);
    setError(null);

    try {
      await setPassword(token, password);
      setSuccess(true);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Something went wrong. Please try again."
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter") handleSubmit();
  }

  // ---------------------------------------------------------------------------
  // Render: success
  // ---------------------------------------------------------------------------

  if (success) {
    return (
      <div className="card token-view">
        <p className="card-title">Password set</p>
        <p className="card-subtitle">
          Your password has been set successfully. You can now sign in.
        </p>
        <button
          className="btn btn-primary"
          onClick={onComplete}
          style={{ marginTop: 16, width: "100%" }}
        >
          Go to login
        </button>
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // Render: no token (invalid/missing link)
  // ---------------------------------------------------------------------------

  if (!token && error) {
    return (
      <div className="card token-view">
        <p className="card-title">Setup link invalid</p>
        <div className="alert alert-error" style={{ marginTop: 12 }}>
          {error}
        </div>
        <button
          className="btn btn-ghost"
          onClick={onComplete}
          style={{ marginTop: 16, fontSize: 13 }}
        >
          Back to login
        </button>
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // Render: set password form
  // ---------------------------------------------------------------------------

  return (
    <div className="card token-view">
      <p className="card-title">Set your password</p>
      <p className="card-subtitle">
        Choose a strong password of at least {MIN_LENGTH} characters.
      </p>

      <div className="field" style={{ marginBottom: 12 }}>
        <label htmlFor="new-password-input">New password</label>
        <input
          id="new-password-input"
          type="password"
          value={password}
          onChange={(e) => setPasswordValue(e.target.value)}
          onKeyDown={handleKeyDown}
          autoComplete="new-password"
          disabled={isSubmitting}
          autoFocus
        />

        {/* Strength meter — only shown when the user has typed something. */}
        {password.length > 0 && (
          <div style={{ marginTop: 8 }}>
            <div
              style={{
                display: "flex",
                gap: 4,
                height: 6,
                borderRadius: 3,
                overflow: "hidden",
              }}
            >
              {[0, 1, 2, 3].map((i) => (
                <div
                  key={i}
                  style={{
                    flex: 1,
                    borderRadius: 3,
                    backgroundColor: i <= score - 1 ? SCORE_COLORS[score] : "#e2e8f0",
                    transition: "background-color 0.2s",
                  }}
                />
              ))}
            </div>
            <p
              style={{
                fontSize: 12,
                marginTop: 4,
                color: SCORE_COLORS[score],
              }}
            >
              {SCORE_LABELS[score]}
            </p>
            {/* Show warning or first suggestion as actionable feedback. */}
            {(warning || suggestions.length > 0) && (
              <p style={{ fontSize: 12, marginTop: 2, color: "#718096" }}>
                {warning || suggestions[0]}
              </p>
            )}
          </div>
        )}
      </div>

      <div className="field" style={{ marginBottom: 16 }}>
        <label htmlFor="confirm-password-input">Confirm password</label>
        <input
          id="confirm-password-input"
          type="password"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          onKeyDown={handleKeyDown}
          autoComplete="new-password"
          disabled={isSubmitting}
        />
        {confirm.length > 0 && !passwordsMatch && (
          <p style={{ fontSize: 12, marginTop: 4, color: "#e53e3e" }}>
            Passwords do not match.
          </p>
        )}
      </div>

      <button
        className="btn btn-primary"
        onClick={handleSubmit}
        disabled={!canSubmit}
        style={{ width: "100%" }}
      >
        {isSubmitting ? (
          <>
            <span className="spinner" />
            Setting password…
          </>
        ) : (
          "Set password"
        )}
      </button>

      {/* Server-side error (expired token, weak password rejected by server, etc.) */}
      {error && (
        <div className="alert alert-error" style={{ marginTop: 12 }}>
          {error}
          {error.includes("expired") && (
            <span>
              {" "}
              <button
                className="btn btn-ghost"
                onClick={onComplete}
                style={{ fontSize: 13, padding: 0 }}
              >
                Return to login
              </button>{" "}
              to request a new link.
            </span>
          )}
        </div>
      )}
    </div>
  );
}
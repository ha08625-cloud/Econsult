/**
 * LoginView.tsx — two-step 2FA login component.
 *
 * Step 1 ("login" state): Email and password inputs.
 *   Calls POST /admin/auth/login.
 *   On success, the server has generated an OTP and queued its delivery.
 *   Advances to step 2.
 *
 * Step 2 ("code" state): 6-digit OTP input.
 *   Calls POST /admin/auth/verify.
 *   On success, calls onSuccess() so App can re-fetch conditions and
 *   transition to EditorView. The session cookie is set by the server.
 *
 * "Forgot / Set up password?" link:
 *   If the email field is non-empty, calls POST /admin/auth/request-reset
 *   and displays a generic confirmation message. If the email field is
 *   empty, prompts the user to enter their email first.
 */

import { useState } from "react";
import { login, verifyMfaCode, requestPasswordReset } from "../api";

interface Props {
  onSuccess: () => void;
}

type Step = "login" | "code";

export default function LoginView({ onSuccess }: Props) {
  const [step, setStep] = useState<Step>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resetMessage, setResetMessage] = useState<string | null>(null);

  // ---------------------------------------------------------------------------
  // Step 1: email + password submission
  // ---------------------------------------------------------------------------

  async function handleLoginSubmit() {
    const trimmedEmail = email.trim().toLowerCase();
    if (!trimmedEmail || !password) return;

    setIsSubmitting(true);
    setError(null);
    setResetMessage(null);

    try {
      await login(trimmedEmail, password);
      setStep("code");
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

  function handleLoginKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter") handleLoginSubmit();
  }

  // ---------------------------------------------------------------------------
  // Forgot / Set up password
  // ---------------------------------------------------------------------------

  async function handleForgotPassword() {
    const trimmedEmail = email.trim().toLowerCase();
    if (!trimmedEmail) {
      setError("Enter your email address above first.");
      return;
    }

    setResetMessage(null);
    setError(null);

    // requestPasswordReset always resolves — server always returns 200.
    await requestPasswordReset(trimmedEmail);

    setResetMessage(
      "If this email is registered, you will receive a setup link shortly."
    );
  }

  // ---------------------------------------------------------------------------
  // Step 2: OTP submission
  // ---------------------------------------------------------------------------

  async function handleCodeSubmit() {
    const trimmed = code.trim();
    if (!trimmed) return;

    setIsSubmitting(true);
    setError(null);

    try {
      await verifyMfaCode(email.trim().toLowerCase(), trimmed);
      onSuccess();
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Invalid or expired code. Please try again."
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  function handleCodeKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter") handleCodeSubmit();
  }

  function handleBackToLogin() {
    setStep("login");
    setCode("");
    setError(null);
  }

  // ---------------------------------------------------------------------------
  // Render: step 1 — login
  // ---------------------------------------------------------------------------

  if (step === "login") {
    return (
      <div className="card token-view">
        <p className="card-title">Admin login</p>
        <p className="card-subtitle">
          Enter your email address and password.
        </p>

        <div className="field" style={{ marginBottom: 12 }}>
          <label htmlFor="email-input">Email address</label>
          <input
            id="email-input"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            onKeyDown={handleLoginKeyDown}
            placeholder="you@example.nhs.net"
            autoComplete="email"
            disabled={isSubmitting}
          />
        </div>

        <div className="field" style={{ marginBottom: 16 }}>
          <label htmlFor="password-input">Password</label>
          <input
            id="password-input"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            onKeyDown={handleLoginKeyDown}
            autoComplete="current-password"
            disabled={isSubmitting}
          />
        </div>

        <button
          className="btn btn-primary"
          onClick={handleLoginSubmit}
          disabled={isSubmitting || !email.trim() || !password}
          style={{ width: "100%" }}
        >
          {isSubmitting ? (
            <>
              <span className="spinner" />
              Signing in…
            </>
          ) : (
            "Sign in"
          )}
        </button>

        {error && (
          <div className="alert alert-error" style={{ marginTop: 12 }}>
            {error}
          </div>
        )}

        {resetMessage && (
          <div className="alert alert-info" style={{ marginTop: 12 }}>
            {resetMessage}
          </div>
        )}

        <button
          className="btn btn-ghost"
          onClick={handleForgotPassword}
          disabled={isSubmitting}
          style={{ marginTop: 16, fontSize: 13 }}
        >
          Forgot / Set up password?
        </button>
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // Render: step 2 — OTP
  // ---------------------------------------------------------------------------

  return (
    <div className="card token-view">
      <p className="card-title">Enter your code</p>
      <p className="card-subtitle">
        A 6-digit security code was sent to{" "}
        <strong>{email.trim().toLowerCase()}</strong>. The code expires in 10
        minutes.
      </p>

      <div className="form-row">
        <div className="field">
          <label htmlFor="code-input">Security code</label>
          <input
            id="code-input"
            type="text"
            inputMode="numeric"
            pattern="[0-9]{6}"
            maxLength={6}
            value={code}
            onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
            onKeyDown={handleCodeKeyDown}
            placeholder="000000"
            autoComplete="one-time-code"
            disabled={isSubmitting}
            autoFocus
          />
        </div>
        <button
          className="btn btn-primary"
          onClick={handleCodeSubmit}
          disabled={isSubmitting || code.trim().length !== 6}
          style={{ marginTop: 22 }}
        >
          {isSubmitting ? (
            <>
              <span className="spinner" />
              Verifying…
            </>
          ) : (
            "Verify"
          )}
        </button>
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      <button
        className="btn btn-ghost"
        onClick={handleBackToLogin}
        disabled={isSubmitting}
        style={{ marginTop: 12, fontSize: 13 }}
      >
        Back to login
      </button>
    </div>
  );
}
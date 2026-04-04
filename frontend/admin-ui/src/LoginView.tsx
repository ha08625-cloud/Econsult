/**
 * LoginView.tsx — two-step MFA login component.
 *
 * Step 1: email input. Calls POST /admin/auth/request-code.
 *         On success, advances to step 2.
 *
 * Step 2: 6-digit code input. Calls POST /admin/auth/verify.
 *         On success, calls onSuccess() so App can re-fetch conditions
 *         and transition to EditorView. The session cookie is set by
 *         the server — this component does not handle it directly.
 *
 * On any 401 received while already in EditorView (detected by App),
 * App transitions back to LoginView. Any unsaved data in EditorView
 * is lost — this is intentional given the 24-hour session TTL and
 * infrequent use pattern.
 */

import { useState } from "react";
import { requestMfaCode, verifyMfaCode } from "./api";

interface Props {
  onSuccess: () => void;
}

type Step = "email" | "code";

export default function LoginView({ onSuccess }: Props) {
  const [step, setStep] = useState<Step>("email");
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // ---------------------------------------------------------------------------
  // Step 1: email submission
  // ---------------------------------------------------------------------------

  async function handleEmailSubmit() {
    const trimmed = email.trim().toLowerCase();
    if (!trimmed) return;

    setIsSubmitting(true);
    setError(null);

    try {
      await requestMfaCode(trimmed);
      setStep("code");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
  }

  function handleEmailKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter") handleEmailSubmit();
  }

  // ---------------------------------------------------------------------------
  // Step 2: code submission
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

  function handleBackToEmail() {
    setStep("email");
    setCode("");
    setError(null);
  }

  // ---------------------------------------------------------------------------
  // Render: step 1 — email
  // ---------------------------------------------------------------------------

  if (step === "email") {
    return (
      <div className="card token-view">
        <p className="card-title">Admin login</p>
        <p className="card-subtitle">
          Enter your admin email address. A one-time security code will be sent to you.
        </p>

        <div className="form-row">
          <div className="field">
            <label htmlFor="email-input">Email address</label>
            <input
              id="email-input"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              onKeyDown={handleEmailKeyDown}
              placeholder="you@example.nhs.net"
              autoComplete="email"
              disabled={isSubmitting}
            />
          </div>
          <button
            className="btn btn-primary"
            onClick={handleEmailSubmit}
            disabled={isSubmitting || email.trim() === ""}
            style={{ marginTop: 22 }}
          >
            {isSubmitting ? (
              <>
                <span className="spinner" />
                Sending…
              </>
            ) : (
              "Send code"
            )}
          </button>
        </div>

        {error && <div className="alert alert-error">{error}</div>}
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // Render: step 2 — code
  // ---------------------------------------------------------------------------

  return (
    <div className="card token-view">
      <p className="card-title">Enter your code</p>
      <p className="card-subtitle">
        A 6-digit security code was sent to <strong>{email.trim().toLowerCase()}</strong>.
        The code expires in 10 minutes.
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
        onClick={handleBackToEmail}
        disabled={isSubmitting}
        style={{ marginTop: 12, fontSize: 13 }}
      >
        Use a different email address
      </button>
    </div>
  );
}
import { PageShell, InlineError } from "../layout";
import type { SafetyWarningFetchState } from "../types";

export type { SafetyWarningFetchState };

interface SafetyWarningScreenProps {
  safetyWarningFetchState: SafetyWarningFetchState;
  practiceName: string | null;
  safetyConfirmed: boolean;
  practiceIsOpen: boolean | null;
  availabilityClosedMessage: string | null;
  afterHoursNotice: string | null;
  onConfirmChange: (confirmed: boolean) => void;
  onRetry: () => void;
  onContinue: () => void;
}

export default function SafetyWarningScreen({
  safetyWarningFetchState,
  practiceName,
  safetyConfirmed,
  practiceIsOpen,
  availabilityClosedMessage,
  afterHoursNotice,
  onConfirmChange,
  onRetry,
  onContinue,
}: SafetyWarningScreenProps) {
  const isClosed = practiceIsOpen === false;

  // Logic to handle string splitting for the safety warning
  const safetyLines = safetyWarningFetchState.status === "success" 
    ? safetyWarningFetchState.text.split("\n") 
    : [];
  
  const introLine = safetyLines[0];
  const symptomLines = safetyLines.slice(1);

  // Hard block if practice is closed
  if (isClosed) {
    return (
      <PageShell practiceName={practiceName}>
        <h1>This service is currently closed</h1>
        <div className="alert alert-warning" style={{ marginBottom: "24px" }}>
          <p style={{ margin: 0 }}>
            {availabilityClosedMessage || "This practice is not currently accepting online forms."}
          </p>
        </div>
        <p>
          If you need urgent medical help that cannot wait until the practice re-opens, 
          please contact 111 or, in an emergency, call 999.
        </p>
      </PageShell>
    );
  }

  return (
    <PageShell practiceName={practiceName}>
      <h1>Before you continue</h1>

      {safetyWarningFetchState.status === "loading" && (
        <div
          className="status-container"
          style={{ minHeight: "200px" }}
          role="status"
          aria-live="polite"
        >
          <p className="status-text">Loading safety information...</p>
        </div>
      )}

      {safetyWarningFetchState.status === "error" && (
        <div style={{ marginBottom: "24px" }}>
          <InlineError message={safetyWarningFetchState.message} />
          <div className="btn-row">
            <button className="btn btn-primary" onClick={onRetry}>
              Try again
            </button>
          </div>
        </div>
      )}

      {safetyWarningFetchState.status === "success" && (
        <>
          <div className="alert alert-warning" style={{ marginBottom: "24px" }}>
            <strong style={{ display: "block", marginBottom: "12px", fontSize: "1.1rem" }}>
              <span className="sr-only">Important: </span>
              Read before continuing
            </strong>

            <p style={{ marginBottom: "12px", fontWeight: 500 }}>{introLine}</p>

            <ul id="safety-warning-list" style={{ paddingLeft: "24px", margin: 0 }}>
              {symptomLines.map((line, i) => (
                line.trim() && <li key={i} style={{ marginBottom: "6px" }}>{line}</li>
              ))}
            </ul>
          </div>

          {afterHoursNotice && (
            <div className="alert alert-info" style={{ marginBottom: "24px" }}>
              <p style={{ margin: 0 }}>{afterHoursNotice}</p>
            </div>
          )}

          <div className="confirm-checkbox-row">
            <label className="confirm-checkbox-label">
              <input
                type="checkbox"
                checked={safetyConfirmed}
                onChange={(e) => onConfirmChange(e.target.checked)}
                aria-describedby="safety-warning-list"
              />
              <span>I confirm that none of the above apply to me</span>
            </label>
          </div>

          {!safetyConfirmed && (
            <p className="safety-gate-hint">
              If any of the above apply to you, please call 999 or go to A&amp;E
              immediately. Do not use this form.
            </p>
          )}

          <div className="btn-row">
            <button
              className="btn btn-primary"
              disabled={!safetyConfirmed}
              onClick={onContinue}
            >
              Continue
            </button>
          </div>
        </>
      )}
    </PageShell>
  );
}
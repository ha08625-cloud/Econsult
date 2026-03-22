import { PageShell, InlineError } from "../layout";
import type { SafetyWarningFetchState, PracticeNameFetchState } from "../types";

// SafetyWarningFetchState and PracticeNameFetchState are defined in types.ts.
// They are re-exported here for backwards compatibility in case any other
// file imports them from this location — but new imports should use types.ts.
export type { SafetyWarningFetchState, PracticeNameFetchState };

interface SafetyWarningScreenProps {
  safetyWarningFetchState: SafetyWarningFetchState;
  practiceNameFetchState: PracticeNameFetchState;
  safetyConfirmed: boolean;
  practiceIsOpen: boolean | null;
  availabilityClosedMessage: string | null;
  afterHoursNotice: string | null;
  onConfirmChange: (confirmed: boolean) => void;
  onRetry: () => void;
  onPracticeRetry: () => void;
  onContinue: () => void;
}

export default function SafetyWarningScreen({
  safetyWarningFetchState,
  practiceNameFetchState,
  safetyConfirmed,
  practiceIsOpen,
  availabilityClosedMessage,
  afterHoursNotice,
  onConfirmChange,
  onRetry,
  onPracticeRetry,
  onContinue,
}: SafetyWarningScreenProps) {
  // Practice is closed: is_open is explicitly false (not null, not true).
  const isClosed = practiceIsOpen === false;

  const practiceName =
    practiceNameFetchState.status === "success"
      ? practiceNameFetchState.name
      : null;

  return (
    <PageShell practiceName={practiceName}>
      <h1>Before you continue</h1>

      {/* Closed message banner — above safety warning */}
      {isClosed && availabilityClosedMessage && (
        <div className="alert alert-warning" style={{ marginBottom: "16px" }}>
          <strong>This service is currently closed</strong>
          <p style={{ margin: "8px 0 0 0" }}>{availabilityClosedMessage}</p>
        </div>
      )}

      {isClosed && !availabilityClosedMessage && (
        <div className="alert alert-warning" style={{ marginBottom: "16px" }}>
          <strong>This service is currently closed</strong>
        </div>
      )}

      {safetyWarningFetchState.status === "loading" && (
        <p className="status-text">Loading...</p>
      )}

      {safetyWarningFetchState.status === "error" && (
        <>
          <InlineError message={safetyWarningFetchState.message} />
          <div className="btn-row">
            <button className="btn btn-primary" onClick={onRetry}>
              Try again
            </button>
          </div>
        </>
      )}

      {safetyWarningFetchState.status === "success" && (
        <>
          <div className="alert alert-danger">
            <strong>Important — read before continuing</strong>
            <p>{safetyWarningFetchState.text}</p>
          </div>

          {/* After-hours notice — below safety warning, above form controls */}
          {afterHoursNotice && !isClosed && (
            <div className="alert alert-info" style={{ marginBottom: "16px" }}>
              <p style={{ margin: 0 }}>{afterHoursNotice}</p>
            </div>
          )}

          {/* Practice name fetch error — independent of safety warning error */}
          {practiceNameFetchState.status === "error" && (
            <>
              <InlineError message={practiceNameFetchState.message} />
              <div className="btn-row">
                <button className="btn btn-secondary" onClick={onPracticeRetry}>
                  Try again
                </button>
              </div>
            </>
          )}

          <div className="safety-confirm-row">
            <label className="safety-confirm-label">
              <input
                type="checkbox"
                checked={safetyConfirmed}
                onChange={(e) => onConfirmChange(e.target.checked)}
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
              disabled={
                !safetyConfirmed ||
                isClosed ||
                practiceNameFetchState.status !== "success"
              }
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
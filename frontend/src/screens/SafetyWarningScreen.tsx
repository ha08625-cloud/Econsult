import { PageShell, InlineError } from "../layout";
import type { SafetyWarningFetchState, PracticeNameFetchState } from "../types";

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
  const isClosed = practiceIsOpen === false;

  const practiceName =
    practiceNameFetchState.status === "success"
      ? practiceNameFetchState.name
      : null;

  const safetyLines = safetyWarningFetchState.status === "success" 
    ? safetyWarningFetchState.text.split("\n") 
    : [];
  
  const introLine = safetyLines[0];
  const symptomLines = safetyLines.slice(1);

  if (isClosed) {
    return (
      <PageShell practiceName={practiceName}>
        <h1>This service is currently closed</h1>
        <div className="nhsuk-warning-callout">
           <h2 className="nhsuk-warning-callout__label">
            Check the practice opening times
          </h2>
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
        <div className="status-container" style={{ minHeight: "200px" }}>
          <p className="status-text">Loading safety information...</p>
        </div>
      )}

      {safetyWarningFetchState.status === "error" && (
        <div style={{ marginBottom: "24px" }}>
          <InlineError message={safetyWarningFetchState.message} />
          <div className="btn-row">
            <button className="btn btn-secondary" onClick={onRetry}>
              Try again
            </button>
          </div>
        </div>
      )}

      {safetyWarningFetchState.status === "success" && (
        <>
          <div className="nhsuk-warning-callout">
            <h2 className="nhsuk-warning-callout__label">
              <span className="nhsuk-u-visually-hidden">Important: </span>
              Read before continuing
            </h2>
            
            <p style={{ fontWeight: 700, marginBottom: "12px" }}>{introLine}</p>
            
            <ul>
              {symptomLines.map((line, i) => (
                line.trim() && <li key={i}>{line}</li>
              ))}
            </ul>
          </div>

          {afterHoursNotice && (
            <div className="alert alert-info" style={{ marginBottom: "24px" }}>
              <p style={{ margin: 0 }}>{afterHoursNotice}</p>
            </div>
          )}

          {practiceNameFetchState.status === "error" && (
            <div style={{ marginBottom: "24px" }}>
              <InlineError message={practiceNameFetchState.message} />
              <div className="btn-row">
                <button className="btn btn-secondary" onClick={onPracticeRetry}>
                  Retry loading practice name
                </button>
              </div>
            </div>
          )}

          <div className="nhsuk-checkboxes__item">
            <input
              className="nhsuk-checkboxes__input"
              id="safety-confirm"
              type="checkbox"
              checked={safetyConfirmed}
              onChange={(e) => onConfirmChange(e.target.checked)}
            />
            <label className="nhsuk-label nhsuk-checkboxes__label" htmlFor="safety-confirm">
              I confirm that none of the above apply to me
            </label>
          </div>

          {!safetyConfirmed && (
             <InlineError message="If any of the above apply to you, please call 999 or go to A&E immediately. Do not use this form." />
          )}

          <div className="btn-row">
            <button
              className="btn btn-primary"
              disabled={
                !safetyConfirmed ||
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

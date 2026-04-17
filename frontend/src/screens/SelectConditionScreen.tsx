[span_0](start_span)import { useId } from "react";[span_0](end_span)
[span_1](start_span)import { PageShell } from "../layout";[span_1](end_span)
import ConditionCombobox from "../ConditionCombobox";
[span_2](start_span)import type { ConditionSummary } from "../types";[span_2](end_span)

interface SelectConditionScreenProps {
  [span_3](start_span)practiceName: string | null;[span_3](end_span)
  // null means the condition list has not yet loaded
  [span_4](start_span)conditions: ConditionSummary[] | null;[span_4](end_span)
  [span_5](start_span)selectedConditionId: string | null;[span_5](end_span)
  [span_6](start_span)onConditionChange: (id: string | null) => void;[span_6](end_span)
  [span_7](start_span)onContinue: () => void;[span_7](end_span)
  [span_8](start_span)onBlankForm: () => void;[span_8](end_span)
  [span_9](start_span)onBack: () => void;[span_9](end_span)
}

export default function SelectConditionScreen({
  practiceName,
  conditions,
  selectedConditionId,
  onConditionChange,
  onContinue,
  onBlankForm,
  onBack,
}: SelectConditionScreenProps) {
  [span_10](start_span)const comboboxId = useId();[span_10](end_span)

  return (
    [span_11](start_span)<PageShell practiceName={practiceName}>[span_11](end_span)
      <div className="screen-card">
        [span_12](start_span)<h1>Start your consultation</h1>[span_12](end_span)

        {conditions === null ? (
          /* Use status-container for consistent loading layouts */
          <div className="status-container" style={{ padding: 'var(--space-xl)' }}>
            <p className="status-text">Loading...</p>
          </div>
        ) : (
          <>
            <div className="field">
              {/* Link the label to the dynamic ID for accessibility */}
              [span_13](start_span)[span_14](start_span)<label htmlFor={comboboxId}>[span_13](end_span)[span_14](end_span)
                [span_15](start_span)What is your consultation about?[span_15](end_span)
              </label>
              <ConditionCombobox
                id={comboboxId}
                [span_16](start_span)conditions={conditions}[span_16](end_span)
                [span_17](start_span)selectedId={selectedConditionId}[span_17](end_span)
                [span_18](start_span)onChange={onConditionChange}[span_18](end_span)
              />
            </div>

            <div className="btn-row">
              <button className="btn btn-secondary" onClick={onBack}>
                Back
              </button>
              <button
                className="btn btn-primary"
                [span_19](start_span)disabled={selectedConditionId === null}[span_19](end_span)
                [span_20](start_span)onClick={onContinue}[span_20](end_span)
              >
                Continue
              </button>
            </div>

            {/* Use form-section for standardized separation and borders */}
            <div className="form-section">
              <p className="screen-description">
                If you cannot find a condition that matches your problem, you can
                [span_21](start_span)use a blank form instead.[span_21](end_span)
              </p>
              <button className="btn btn-secondary" onClick={onBlankForm}>
                Use blank form
              </button>
            </div>
          </>
        )}
      </div>
    </PageShell>
  );
}

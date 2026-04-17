import { useId } from "react";
import { PageShell } from "../layout";
import ConditionCombobox from "../ConditionCombobox";
import type { ConditionSummary } from "../types";

interface SelectConditionScreenProps {
  practiceName: string | null;
  // null means the condition list has not yet loaded
  conditions: ConditionSummary[] | null;
  selectedConditionId: string | null;
  onConditionChange: (id: string | null) => void;
  onContinue: () => void;
  onBlankForm: () => void;
  onBack: () => void;
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
  const comboboxId = useId();

  return (
    <PageShell practiceName={practiceName}>
      <div className="screen-card">
        <h1>Start your consultation</h1>

        {conditions === null ? (
          <div className="status-container" style={{ padding: 'var(--space-xl)' }}>
            <p className="status-text">Loading...</p>
          </div>
        ) : (
          <>
            <div className="field">
              <label htmlFor={comboboxId}>
                What is your consultation about?
              </label>
              <ConditionCombobox
                id={comboboxId}
                conditions={conditions}
                selectedId={selectedConditionId}
                onChange={onConditionChange}
              />
            </div>

            <div className="btn-row">
              <button 
                type="button" 
                className="btn btn-secondary" 
                onClick={onBack}
              >
                Back
              </button>
              <button
                type="button"
                className="btn btn-primary"
                disabled={selectedConditionId === null}
                onClick={onContinue}
              >
                Continue
              </button>
            </div>

            <div className="form-section">
              <p className="screen-description">
                If you cannot find a condition that matches your problem, you can
                use a blank form instead.
              </p>
              <button 
                type="button" 
                className="btn btn-secondary" 
                onClick={onBlankForm}
              >
                Use blank form
              </button>
            </div>
          </>
        )}
      </div>
    </PageShell>
  );
}

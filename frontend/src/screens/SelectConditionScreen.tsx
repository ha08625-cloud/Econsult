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
}

export default function SelectConditionScreen({
  practiceName,
  conditions,
  selectedConditionId,
  onConditionChange,
  onContinue,
  onBlankForm,
}: SelectConditionScreenProps) {
  return (
    <PageShell practiceName={practiceName}>
      <h1>Start your consultation</h1>

      {conditions === null ? (
        <p className="status-text">Loading...</p>
      ) : (
        <>
          <div className="field">
            <label htmlFor="condition-combobox-input">
              What is your consultation about?
            </label>
            <ConditionCombobox
              conditions={conditions}
              selectedId={selectedConditionId}
              onChange={onConditionChange}
            />
          </div>

          <div className="btn-row">
            <button
              className="btn btn-primary"
              disabled={selectedConditionId === null}
              onClick={onContinue}
            >
              Continue
            </button>
          </div>

          <hr className="divider" />

          <p style={{ color: "var(--text-muted)", fontSize: "14px", marginBottom: "12px" }}>
            If you cannot find a condition that matches your problem, you can
            use a blank form instead.
          </p>
          <button className="btn btn-secondary" onClick={onBlankForm}>
            Use blank form
          </button>
        </>
      )}
    </PageShell>
  );
}
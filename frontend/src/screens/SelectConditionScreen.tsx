// File path: frontend/src/screens/SelectConditionScreen.tsx
import { PageShell } from "../layout";
import { useFocusHeading } from "../useFocusHeading";
import ConditionCombobox from "../ConditionCombobox";
import type { ConditionSummary } from "../types";

interface SelectConditionScreenProps {
  practiceName: string | null;
  // null means the condition list has not yet loaded
  conditions: ConditionSummary[] | null;
  selectedConditionId: string | null;
  // Bumped by App.tsx to force ConditionCombobox to remount (and re-run its
  // mount-time label lookup) when the parent needs the displayed text to
  // revert to selectedConditionId without changing selectedConditionId's
  // identity-based React reconciliation otherwise wouldn't catch.
  comboboxResetKey: number;
  onConditionChange: (id: string | null) => void;
  onContinue: () => void;
  onBlankForm: () => void;
  onBack: () => void;
}

export default function SelectConditionScreen({
  practiceName,
  conditions,
  selectedConditionId,
  comboboxResetKey,
  onConditionChange,
  onContinue,
  onBlankForm,
  onBack,
}: SelectConditionScreenProps) {
  // Focus the heading once conditions transition from null (loading) to
  // loaded, so screen reader users are notified that the form is ready.
  const headingRef = useFocusHeading(conditions);

  return (
    <PageShell practiceName={practiceName}>
      {/* tabIndex={-1} allows programmatic focus without entering the tab order */}
      <h1 ref={headingRef} tabIndex={-1}>Start your consultation</h1>

      {conditions === null ? (
        // Issue 2: role="status" causes screen readers to announce "Loading..."
        // when this container mounts.
        <div role="status" className="status-container" style={{ padding: 'var(--space-xl)' }}>
          <p className="status-text">Loading...</p>
        </div>
      ) : (
        <>
          <div className="field">
            <label id="condition-label">
              What is your consultation about?
            </label>
            <ConditionCombobox
              key={comboboxResetKey}
              conditions={conditions}
              selectedId={selectedConditionId}
              onChange={onConditionChange}
              labelId="condition-label"
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
            {/* Issue 3: id links this hint to the button via aria-describedby */}
            <p id="blank-form-hint" className="screen-description">
              If you cannot find a condition that matches your problem, you can
              use a blank form instead.
            </p>
            <button
              type="button"
              className="btn btn-secondary"
              aria-describedby="blank-form-hint"
              onClick={onBlankForm}
            >
              Use blank form
            </button>
          </div>
        </>
      )}
    </PageShell>
  );
}
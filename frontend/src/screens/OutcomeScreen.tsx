import { useRef, useState } from "react";
import { PageShell } from "../layout";
import { useFocusHeading } from "../useFocusHeading";
import type { ConsultationOutcome } from "../types";
import outcomes from "../../consultation_outcomes.json";

interface OutcomeScreenProps {
  practiceName: string | null;
  onContinue: (outcome: ConsultationOutcome) => void;
  onBack: () => void;
}

export default function OutcomeScreen({
  practiceName,
  onContinue,
  onBack,
}: OutcomeScreenProps) {
  const [selected, setSelected] = useState<ConsultationOutcome | null>(null);
  const headingRef = useFocusHeading();
  const hintRef = useRef<HTMLParagraphElement>(null);

  /**
   * Type Guard helper to safely cast string values from JSON to the
   * ConsultationOutcome union defined in types.ts.
   */
  const handleSelection = (value: string) => {
    setSelected(value as ConsultationOutcome);
  };

  return (
    <PageShell practiceName={practiceName}>
      <h1 ref={headingRef} tabIndex={-1}>What do you need today?</h1>
      <p className="screen-description">
        Please select the option that best describes your request.
      </p>

      <fieldset className="field" role="radiogroup" aria-required="true">
        <legend>Request type</legend>
        <div className="selection-grid">
          {outcomes.map((outcome) => (
            <label
              key={outcome.value}
              className={`selection-card ${
                selected === outcome.value ? "selected" : ""
              }`}
            >
              <input
                type="radio"
                name="consultation_outcome"
                value={outcome.value}
                checked={selected === outcome.value}
                onChange={() => handleSelection(outcome.value)}
                aria-required="true"
              />
              <span className="selection-label">{outcome.label}</span>
            </label>
          ))}
        </div>
        {selected === null && (
          <p className="field-hint" aria-live="polite" ref={hintRef} tabIndex={-1}>
            Select an option to continue.
          </p>
        )}
      </fieldset>

      <div className="btn-row">
        <button className="btn btn-secondary" onClick={onBack}>
          Back
        </button>
        <button
          className="btn btn-primary"
          onClick={() => {
            if (selected === null) {
              hintRef.current?.focus();
              return;
            }
            onContinue(selected);
          }}
        >
          Continue
        </button>
      </div>
    </PageShell>
  );
}
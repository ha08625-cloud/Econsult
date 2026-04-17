import { useState } from "react";
import { PageShell } from "../layout";
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

  /**
   * Type Guard helper to safely cast string values from JSON to the 
   * ConsultationOutcome union defined in types.ts.
   */
  const handleSelection = (value: string) => {
    setSelected(value as ConsultationOutcome);
  };

  return (
    <PageShell practiceName={practiceName}>
      <h1>What do you need today?</h1>
      <p className="screen-description">
        Please select the option that best describes your request.
      </p>

      {/* Urgent Care Notice: Standardized with Design Tokens */}
      <div
        className="alert alert-info"
        style={{
          background: "var(--nhs-blue-light)",
          border: "1px solid var(--nhs-blue)",
          borderRadius: "var(--radius)",
          padding: "var(--space-md)",
          marginBottom: "var(--space-lg)",
          fontSize: "15px",
          color: "var(--text-label)",
        }}
      >
        <strong>Do not use this form for urgent matters.</strong> If you need
        urgent medical attention, call <strong>111</strong> or <strong>999</strong>.
      </div>

      <div className="form-section">
        <div className="field">
          <label>Request type</label>
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
                />
                <span className="selection-label">{outcome.label}</span>
              </label>
            ))}
          </div>
        </div>
      </div>

      <div className="btn-row">
        <button className="btn btn-secondary" onClick={onBack}>
          Back
        </button>
        <button
          className="btn btn-primary"
          disabled={selected === null}
          onClick={() => {
            if (selected !== null) onContinue(selected);
          }}
        >
          Continue
        </button>
      </div>
    </PageShell>
  );
}

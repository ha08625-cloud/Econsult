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

  return (
    <PageShell practiceName={practiceName}>
      <h1>What do you need today?</h1>

      <div
        style={{
          background: "var(--surface-alt, #f0f4fa)",
          border: "1px solid var(--border, #d0d7e3)",
          borderRadius: "6px",
          padding: "12px 16px",
          marginBottom: "24px",
          fontSize: "14px",
          color: "var(--text-muted)",
        }}
      >
        Do not use this form for urgent matters. If you need urgent medical
        attention, call 111 or 999.
      </div>

      <div className="field">
        <label>Please select the option that best describes your request</label>
        <div style={{ display: "flex", flexDirection: "column", gap: "10px", marginTop: "8px" }}>
          {outcomes.map((outcome) => (
            <label
              key={outcome.value}
              style={{
                display: "flex",
                alignItems: "flex-start",
                gap: "10px",
                cursor: "pointer",
                fontSize: "15px",
              }}
            >
              <input
                type="radio"
                name="consultation_outcome"
                value={outcome.value}
                checked={selected === outcome.value}
                onChange={() => setSelected(outcome.value as ConsultationOutcome)}
                style={{ marginTop: "3px", flexShrink: 0 }}
              />
              {outcome.label}
            </label>
          ))}
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
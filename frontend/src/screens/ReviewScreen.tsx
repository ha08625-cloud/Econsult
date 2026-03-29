import { PageShell } from "../layout";
import type { ClientStateView, SafetyMessage } from "../types";
import type { PhotoAttachment } from "../uiTypes";

interface ReviewScreenProps {
  practiceName: string | null;
  clientState: ClientStateView;
  safetyMessages: SafetyMessage[];
  // Photo props — UI implemented in step 7.
  photos: PhotoAttachment[];
  onBack: () => void;
  onContinue: () => void;
}

export default function ReviewScreen({
  practiceName,
  clientState,
  safetyMessages,
  photos: _photos,
  onBack,
  onContinue,
}: ReviewScreenProps) {
  const hasSafetyBlock = safetyMessages.length > 0;

  return (
    <PageShell practiceName={practiceName}>
      <h1>Review your answers</h1>

      <h3>{clientState.condition_label}</h3>

      {clientState.free_text && (
        <div className="description-box mb-md">
          {clientState.free_text}
        </div>
      )}

      <ul className="review-list">
        {clientState.questions.map((q) => (
          <li key={q.answer_key} className="review-item">
            <span className="review-question">{q.question_text}</span>
            <span className="review-answer">
              {q.current_value === null || q.current_value === "" ? (
                <em style={{ color: "var(--text-muted)", fontWeight: 400 }}>
                  Not answered
                </em>
              ) : String(q.current_value) === "true" ? (
                "Yes"
              ) : String(q.current_value) === "false" ? (
                "No"
              ) : (
                String(q.current_value)
              )}
            </span>
          </li>
        ))}
      </ul>

      {clientState.additional_text && (
        <>
          <h3>Additional information</h3>
          <div className="description-box mb-md">
            {clientState.additional_text}
          </div>
        </>
      )}

      {/* Photo thumbnails — implemented in step 7 */}

      {hasSafetyBlock && (
        <div className="alert alert-danger">
          <strong>Important — action required</strong>
          {safetyMessages.map((m) => (
            <p key={m.rule_id}>{m.message}</p>
          ))}
        </div>
      )}

      <div className="btn-row">
        <button className="btn btn-secondary" onClick={onBack}>
          Back
        </button>

        <button
          className="btn btn-primary"
          disabled={hasSafetyBlock}
          onClick={onContinue}
        >
          Continue
        </button>
      </div>
    </PageShell>
  );
}
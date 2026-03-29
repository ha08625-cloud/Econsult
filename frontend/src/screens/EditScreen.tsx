import { useState } from "react";
import { PageShell, InlineError } from "../layout";
import { updateForm } from "../api";
import { friendlyErrorMessage } from "../api";
import type { ClientStateView, SafetyMessage, ClientAnswerReturn } from "../types";
import type { PhotoAttachment } from "../uiTypes";

interface EditScreenProps {
  practiceName: string | null;
  clientState: ClientStateView;
  editableAnswers: Record<string, boolean | string | null>;
  additionalText: string;
  onAnswersChange: (answers: Record<string, boolean | string | null>) => void;
  onAdditionalTextChange: (text: string) => void;
  onContinue: (result: {
    version: number;
    clientState: ClientStateView;
    safetyMessages: SafetyMessage[];
  }) => void;
  onBack: () => void;
  runtimeId: string;
  version: number;
  // Photo props — UI implemented in step 6.
  photos: PhotoAttachment[];
  onPhotosChange: (updated: PhotoAttachment[]) => void;
}

export default function EditScreen({
  practiceName,
  clientState,
  editableAnswers,
  additionalText,
  onAnswersChange,
  onAdditionalTextChange,
  onContinue,
  onBack,
  runtimeId,
  version,
  photos: _photos,
  onPhotosChange: _onPhotosChange,
}: EditScreenProps) {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [screenError, setScreenError] = useState<string | null>(null);

  const allRequiredAnswered = clientState.questions.every((q) => {
    if (!q.required) return true;
    const v = editableAnswers[q.answer_key];
    return v !== null && v !== undefined && v !== "";
  });

  async function handleContinue() {
    setScreenError(null);
    setIsSubmitting(true);
    try {
      const payload: ClientAnswerReturn = {
        runtime_id: runtimeId,
        base_version: version,
        answers: editableAnswers,
        additional_text: additionalText.trim() || null,
      };
      const res = await updateForm(payload);
      onContinue({
        version: res.version,
        clientState: res.client_state,
        safetyMessages: res.safety_messages,
      });
    } catch (e) {
      setScreenError(friendlyErrorMessage(e));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <PageShell practiceName={practiceName}>
      <h1>{clientState.condition_label}</h1>

      {clientState.free_text && (
        <div className="description-box">{clientState.free_text}</div>
      )}

      <form onSubmit={(e) => e.preventDefault()}>
        {clientState.questions.map((q) => (
          <div
            key={q.answer_key}
            className={`question-card${q.suggested ? " suggested" : ""}`}
          >
            <label>
              {q.question_text}
              {q.required && (
                <span style={{ color: "var(--danger)", marginLeft: "4px" }}>*</span>
              )}
            </label>

            {q.answer_type === "boolean" ? (
              <div className="radio-group">
                <label
                  className={`radio-option${
                    editableAnswers[q.answer_key] === true ? " selected" : ""
                  }`}
                >
                  <input
                    type="radio"
                    name={q.answer_key}
                    checked={editableAnswers[q.answer_key] === true}
                    onChange={() => {
                      onAnswersChange({ ...editableAnswers, [q.answer_key]: true });
                      if (screenError) setScreenError(null);
                    }}
                  />
                  Yes
                </label>
                <label
                  className={`radio-option${
                    editableAnswers[q.answer_key] === false ? " selected" : ""
                  }`}
                >
                  <input
                    type="radio"
                    name={q.answer_key}
                    checked={editableAnswers[q.answer_key] === false}
                    onChange={() => {
                      onAnswersChange({ ...editableAnswers, [q.answer_key]: false });
                      if (screenError) setScreenError(null);
                    }}
                  />
                  No
                </label>
              </div>
            ) : (
              <input
                type="text"
                value={(editableAnswers[q.answer_key] as string | null) || ""}
                onChange={(e) => {
                  onAnswersChange({ ...editableAnswers, [q.answer_key]: e.target.value });
                  if (screenError) setScreenError(null);
                }}
              />
            )}

            {q.suggested && (
              <span className="suggested-badge">
                Pre-filled from your description — please check
              </span>
            )}
          </div>
        ))}

        <div className="field mt-md">
          <label htmlFor="additional-text">
            Additional information (optional)
          </label>
          <p
            style={{
              fontSize: "14px",
              color: "var(--text-muted)",
              marginBottom: "8px",
              fontWeight: 400,
            }}
          >
            If you answered yes to any symptoms above, you can give details here.
          </p>
          <textarea
            id="additional-text"
            value={additionalText}
            onChange={(e) => {
              onAdditionalTextChange(e.target.value);
              if (screenError) setScreenError(null);
            }}
            rows={4}
          />
        </div>

        {/* Photo upload section — implemented in step 6 */}

        {screenError && <InlineError message={screenError} />}

        <div className="btn-row">
          <button
            className="btn btn-secondary"
            disabled={isSubmitting}
            onClick={onBack}
          >
            Back
          </button>
          <button
            className="btn btn-primary"
            disabled={!allRequiredAnswered || isSubmitting}
            onClick={handleContinue}
          >
            {isSubmitting ? "Please wait\u2026" : "Review answers"}
          </button>
        </div>
      </form>
    </PageShell>
  );
}
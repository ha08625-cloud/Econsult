import { useState } from "react";
import DOMPurify from "dompurify";
import { PageShell, InlineError } from "../layout";
import { initForm, friendlyErrorMessage } from "../api";
import { initialiseEditableAnswers } from "../helpers";
import { SIGNPOSTING_PURIFY_CONFIG } from "../constants";
import type { PresentationState, ClientStateView } from "../types";

interface FreeTextScreenProps {
  presentationState: PresentationState;
  freeText: string;
  selectedConditionId: string;
  onFreeTextChange: (text: string) => void;
  onContinue: (result: {
    runtimeId: string;
    version: number;
    clientState: ClientStateView;
    editableAnswers: Record<string, boolean | string | null>;
    additionalText: string;
  }) => void;
  onBack: () => void;
  onRetry: () => void;
}

export default function FreeTextScreen({
  presentationState,
  freeText,
  selectedConditionId,
  onFreeTextChange,
  onContinue,
  onBack,
  onRetry,
}: FreeTextScreenProps) {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [screenError, setScreenError] = useState<string | null>(null);

  if (presentationState.status === "loading") {
    return (
      <PageShell>
        <p className="status-text">Loading...</p>
      </PageShell>
    );
  }

  if (presentationState.status === "error") {
    return (
      <PageShell>
        <h1>Something went wrong</h1>
        <InlineError message={presentationState.message} />
        <div className="btn-row">
          <button className="btn btn-secondary" onClick={onBack}>
            Back
          </button>
          <button className="btn btn-primary" onClick={onRetry}>
            Try again
          </button>
        </div>
      </PageShell>
    );
  }

  // status === "success"
  const presentation = presentationState.data;

  async function handleContinue() {
    setScreenError(null);
    setIsSubmitting(true);
    try {
      const res = await initForm(selectedConditionId, freeText || null);
      onContinue({
        runtimeId: res.runtime_id,
        version: res.version,
        clientState: res.client_state,
        editableAnswers: initialiseEditableAnswers(res.client_state),
        additionalText: res.client_state.additional_text ?? "",
      });
    } catch (e) {
      setScreenError(friendlyErrorMessage(e));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <PageShell>
      <h1>{presentation.label}</h1>

      {presentation.practice_signposting && (
        <div
          className="alert alert-info"
          dangerouslySetInnerHTML={{
            __html: DOMPurify.sanitize(
              presentation.practice_signposting,
              SIGNPOSTING_PURIFY_CONFIG
            ),
          }}
        />
      )}

      <div className="field">
        <label htmlFor="free-text-input">
          {presentation.free_text_prompt ?? "Describe your symptoms"}
        </label>
        <textarea
          id="free-text-input"
          value={freeText}
          onChange={(e) => {
            onFreeTextChange(e.target.value);
            if (screenError) setScreenError(null);
          }}
          rows={5}
        />
      </div>

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
          disabled={isSubmitting}
          onClick={handleContinue}
        >
          {isSubmitting ? "Please wait\u2026" : "Continue"}
        </button>
      </div>
    </PageShell>
  );
}
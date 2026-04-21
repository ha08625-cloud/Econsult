import { useRef, useState, useEffect } from "react";
import { PageShell, InlineError } from "../layout";
import { updateForm } from "../api";
import { friendlyErrorMessage } from "../api";
import type { ClientStateView, SafetyMessage, ClientAnswerReturn } from "../types";
import type { PhotoAttachment } from "../uiTypes";
import {
  ALLOWED_MIME_TYPES,
  MAX_FILE_SIZE_BYTES,
  MAX_FILE_COUNT,
  MAX_TOTAL_SIZE_BYTES,
} from "../upload_constants";

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
  photos,
  onPhotosChange,
}: EditScreenProps) {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [screenError, setScreenError] = useState<string | null>(null);
  const [photoError, setPhotoError] = useState<string | null>(null);
  
  const fileInputRef = useRef<HTMLInputElement>(null);
  const summaryRef = useRef<HTMLDivElement>(null);

  // Move focus to the error summary when a new error appears
  useEffect(() => {
    if (screenError || photoError) {
      summaryRef.current?.focus();
    }
  }, [screenError, photoError]);

  const allRequiredAnswered = clientState.questions.every((q) => {
    if (!q.required) return true;
    const v = editableAnswers[q.answer_key];
    return v !== null && v !== undefined && v !== "";
  });

  async function handleContinue() {
    setScreenError(null);
    setPhotoError(null);
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

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    setScreenError(null);
    setPhotoError(null);

    const incoming = Array.from(e.target.files ?? []);
    // Reset the input so the same file can be re-selected after removal
    if (fileInputRef.current) fileInputRef.current.value = "";

    if (incoming.length === 0) return;

    // Per-file type and size checks
    for (const file of incoming) {
      if (!ALLOWED_MIME_TYPES.includes(file.type)) {
        setPhotoError(
          `"${file.name}" is not a supported file type. Please upload JPEG or PNG images only.`
        );
        return;
      }
      if (file.size > MAX_FILE_SIZE_BYTES) {
        const limitMB = (MAX_FILE_SIZE_BYTES / 1_048_576).toFixed(0);
        setPhotoError(
          `"${file.name}" is too large. Each photo must be ${limitMB} MB or smaller.`
        );
        return;
      }
    }

    // Count check — existing + incoming must not exceed MAX_FILE_COUNT
    if (photos.length + incoming.length > MAX_FILE_COUNT) {
      setPhotoError(
        `You can upload a maximum of ${MAX_FILE_COUNT} photos. You currently have ${photos.length}.`
      );
      return;
    }

    // Combined size check — existing bytes + incoming bytes
    const existingBytes = photos.reduce((sum, p) => sum + p.file.size, 0);
    const incomingBytes = incoming.reduce((sum, f) => sum + f.size, 0);
    if (existingBytes + incomingBytes > MAX_TOTAL_SIZE_BYTES) {
      const limitMB = (MAX_TOTAL_SIZE_BYTES / 1_048_576).toFixed(0);
      setPhotoError(
        `The total size of all photos cannot exceed ${limitMB} MB. Please remove a photo or choose smaller files.`
      );
      return;
    }

    // All checks passed — create PhotoAttachment objects and merge
    const newAttachments: PhotoAttachment[] = incoming.map((file) => ({
      file,
      previewUrl: URL.createObjectURL(file),
    }));
    onPhotosChange([...photos, ...newAttachments]);
  }

  function handleRemovePhoto(index: number) {
    const updated = photos.filter((_, i) => i !== index);
    URL.revokeObjectURL(photos[index].previewUrl);
    onPhotosChange(updated);
  }

  const totalBytes = photos.reduce((sum, p) => sum + p.file.size, 0);
  const totalMB = (totalBytes / 1_048_576).toFixed(1);
  const limitMB = (MAX_TOTAL_SIZE_BYTES / 1_048_576).toFixed(0);
  const hasErrors = !!(screenError || photoError);

  return (
    <PageShell practiceName={practiceName}>
      <h1>{clientState.condition_label}</h1>

      {clientState.free_text && (
        <p className="screen-description">{clientState.free_text}</p>
      )}

      {/* Error summary — rendered and focused on failed submission or validation */}
      {hasErrors && (
        <div
          className="error-summary"
          role="alert"
          tabIndex={-1}
          ref={summaryRef}
        >
          <h2 className="error-summary-heading">There is a problem</h2>
          <ul className="error-summary-list">
            {screenError && <li>{screenError}</li>}
            {photoError && <li>{photoError}</li>}
          </ul>
        </div>
      )}

      <form onSubmit={(e) => e.preventDefault()}>
        <div className="form-section">
          {clientState.questions.map((q) => {
            const inputId = `question-${q.answer_key}`;

            if (q.answer_type === "boolean") {
              return (
                <fieldset key={q.answer_key} className="field">
                  <legend>
                    {q.question_text}{" "}
                    {!q.required && <span className="field-label-optional">(optional)</span>}
                  </legend>
                  
                  {q.suggested && (
                    <div className="alert alert-info" style={{ marginBottom: "var(--space-sm)", padding: "8px 12px" }}>
                      <p style={{ margin: 0, fontSize: "14px" }}>
                        Pre-filled from your description — please check
                      </p>
                    </div>
                  )}

                  <div className="selection-grid">
                    <label className={`selection-card ${editableAnswers[q.answer_key] === true ? "selected" : ""}`}>
                      <input
                        type="radio"
                        name={q.answer_key}
                        checked={editableAnswers[q.answer_key] === true}
                        onChange={() => {
                          onAnswersChange({ ...editableAnswers, [q.answer_key]: true });
                          if (screenError) setScreenError(null);
                        }}
                      />
                      <span className="selection-label">Yes</span>
                    </label>
                    <label className={`selection-card ${editableAnswers[q.answer_key] === false ? "selected" : ""}`}>
                      <input
                        type="radio"
                        name={q.answer_key}
                        checked={editableAnswers[q.answer_key] === false}
                        onChange={() => {
                          onAnswersChange({ ...editableAnswers, [q.answer_key]: false });
                          if (screenError) setScreenError(null);
                        }}
                      />
                      <span className="selection-label">No</span>
                    </label>
                  </div>
                </fieldset>
              );
            }

            // Text Questions
            return (
              <div key={q.answer_key} className="field">
                <label htmlFor={inputId}>
                  {q.question_text}{" "}
                  {!q.required && <span className="field-label-optional">(optional)</span>}
                </label>

                {q.suggested && (
                  <div className="alert alert-info" style={{ marginBottom: "var(--space-sm)", padding: "8px 12px" }}>
                    <p style={{ margin: 0, fontSize: "14px" }}>
                      Pre-filled from your description — please check
                    </p>
                  </div>
                )}

                <input
                  id={inputId}
                  type="text"
                  value={(editableAnswers[q.answer_key] as string | null) || ""}
                  onChange={(e) => {
                    onAnswersChange({ ...editableAnswers, [q.answer_key]: e.target.value });
                    if (screenError) setScreenError(null);
                  }}
                />
              </div>
            );
          })}
        </div>

        <div className="form-section">
          <div className="field">
            <label htmlFor="additional-text">
              Additional information{" "}
              <span className="field-label-optional">(optional)</span>
            </label>
            <p id="additional-text-hint" className="field-hint">
              If you answered yes to any symptoms above, you can give details here.
            </p>
            <textarea
              id="additional-text"
              aria-describedby="additional-text-hint"
              value={additionalText}
              onChange={(e) => {
                onAdditionalTextChange(e.target.value);
                if (screenError) setScreenError(null);
              }}
              rows={4}
            />
          </div>
        </div>

        <div className="form-section">
          {/* Photo upload section */}
          <div className={`field ${photoError ? "has-error" : ""}`}>
            <label htmlFor="photo-upload">
              Photos{" "}
              <span className="field-label-optional">(optional)</span>
            </label>
            <p id="photo-upload-hint" className="field-hint">
              You may attach up to {MAX_FILE_COUNT} photos (JPEG or PNG, max{" "}
              {(MAX_FILE_SIZE_BYTES / 1_048_576).toFixed(0)} MB each).
            </p>

            {/* Native visible file input */}
            <input
              id="photo-upload"
              ref={fileInputRef}
              type="file"
              accept="image/jpeg,image/png"
              multiple
              aria-describedby={photoError ? "photo-upload-hint photo-error" : "photo-upload-hint"}
              aria-invalid={!!photoError}
              onChange={handleFileChange}
              style={{ display: "block", marginTop: "var(--space-sm)", marginBottom: "var(--space-sm)" }}
            />

            {photoError && <InlineError message={photoError} />}

            {photos.length > 0 && (
              <p
                style={{
                  fontSize: "14px",
                  color: "var(--text-muted)",
                  marginTop: "8px",
                  marginBottom: "8px",
                }}
              >
                {totalMB} MB of {limitMB} MB used
              </p>
            )}

            {photos.length > 0 && (
              <div
                style={{
                  display: "flex",
                  flexWrap: "wrap",
                  gap: "12px",
                  marginTop: "8px",
                }}
              >
                {photos.map((photo, index) => (
                  <div
                    key={photo.previewUrl}
                    style={{ position: "relative", display: "inline-block" }}
                  >
                    <img
                      src={photo.previewUrl}
                      alt={`Photo ${index + 1}`}
                      style={{
                        height: "80px",
                        width: "80px",
                        objectFit: "cover",
                        borderRadius: "var(--radius)",
                        display: "block",
                      }}
                    />
                    <button
                      type="button"
                      aria-label={`Remove photo ${index + 1}`}
                      onClick={() => handleRemovePhoto(index)}
                      style={{
                        position: "absolute",
                        top: "-6px",
                        right: "-6px",
                        background: "var(--text)",
                        color: "#fff",
                        border: "2px solid #fff",
                        borderRadius: "50%",
                        width: "28px",
                        height: "28px",
                        fontSize: "16px",
                        cursor: "pointer",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        padding: 0,
                        boxShadow: "0 2px 4px rgba(0,0,0,0.2)",
                      }}
                    >
                      <span aria-hidden="true">&times;</span>
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

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
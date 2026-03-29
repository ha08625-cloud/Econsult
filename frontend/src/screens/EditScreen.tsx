import { useRef, useState } from "react";
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

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
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

        {/* Photo upload section */}
        <div className="field mt-md">
          <label>Photos (optional)</label>
          <p
            style={{
              fontSize: "14px",
              color: "var(--text-muted)",
              marginBottom: "8px",
              fontWeight: 400,
            }}
          >
            You may attach up to {MAX_FILE_COUNT} photos (JPEG or PNG, max{" "}
            {(MAX_FILE_SIZE_BYTES / 1_048_576).toFixed(0)} MB each).
          </p>

          <input
            ref={fileInputRef}
            type="file"
            accept="image/jpeg,image/png"
            multiple
            style={{ position: "absolute", opacity: 0, width: 0, height: 0, overflow: "hidden" }}
            aria-label="Upload photos"
            onChange={handleFileChange}
          />

          {photos.length < MAX_FILE_COUNT && (
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => fileInputRef.current?.click()}
            >
              Add photos
            </button>
          )}

          {photos.length > 0 && (
            <p
              style={{
                fontSize: "13px",
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
                      borderRadius: "4px",
                      display: "block",
                    }}
                  />
                  <button
                    type="button"
                    aria-label={`Remove photo ${index + 1}`}
                    onClick={() => handleRemovePhoto(index)}
                    style={{
                      position: "absolute",
                      top: "2px",
                      right: "2px",
                      background: "rgba(0,0,0,0.6)",
                      color: "#fff",
                      border: "none",
                      borderRadius: "50%",
                      width: "20px",
                      height: "20px",
                      fontSize: "12px",
                      cursor: "pointer",
                      lineHeight: "20px",
                      padding: 0,
                      textAlign: "center",
                    }}
                  >
                    &times;
                  </button>
                </div>
              ))}
            </div>
          )}

          {photoError && <InlineError message={photoError} />}
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

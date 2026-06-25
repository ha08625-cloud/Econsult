import { useRef, useState, useEffect, useMemo } from "react";
import { PageShell, InlineError } from "../layout";
import { updateForm } from "../api";
import { friendlyErrorMessage } from "../api";
import type { ClientStateView, SafetyMessage, ClientAnswerReturn } from "../types";
import type { PhotoAttachment } from "../uiTypes";
import {
  ALLOWED_MIME_TYPES,
  MAX_FILE_SIZE_BYTES,
  MAX_TOTAL_SIZE_BYTES,
} from "../upload_constants";

export type PhotoTier = "high" | "standard";

// Per-tier photo count limits enforced on the client.
// These must stay consistent with the _TIER_ATTEMPTS keys in image_sanitizer.py
// and the _VALID_TIERS set in form_router.py.
const TIER_MAX_COUNT: Record<PhotoTier, number> = {
  high: 1,
  standard: 5,
};

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
  photoTier: PhotoTier | null;
  onPhotoTierChange: (tier: PhotoTier) => void;
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
  photoTier,
  onPhotoTierChange,
}: EditScreenProps) {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [screenError, setScreenError] = useState<string | null>(null);
  const [photoError, setPhotoError] = useState<string | null>(null);
  const [isGuideOpen, setIsGuideOpen] = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const summaryRef = useRef<HTMLDivElement>(null);
  const guideCloseRef = useRef<HTMLButtonElement>(null);

  // Move focus to the error summary when a new error appears.
  useEffect(() => {
    if (screenError || photoError) {
      summaryRef.current?.focus();
    }
  }, [screenError, photoError]);

  // Move focus to the close button when the guide modal opens.
  // The close button is the first interactive element and is immediately
  // actionable, making it the correct accessible focus target.
  useEffect(() => {
    if (isGuideOpen) {
      guideCloseRef.current?.focus();
    }
  }, [isGuideOpen]);

  // Attach an Escape key listener while the guide is open.
  useEffect(() => {
    if (!isGuideOpen) return;
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        setIsGuideOpen(false);
      }
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [isGuideOpen]);

  const allRequiredAnswered = clientState.questions.every((q) => {
    if (!q.required) return true;
    const v = editableAnswers[q.answer_key];
    return v !== null && v !== undefined && v !== "";
  });

  // Per-question precision errors for Number questions, derived from the current
  // answers on every render (not set on keystroke) so the gate stays correct
  // across remounts and Back/forward navigation. The raw string is held verbatim
  // in editableAnswers, so a typed trailing zero (e.g. "70.50" when one decimal
  // is allowed) is flagged here even though it would be sent as 70.5.
  const numberPrecisionErrors = useMemo(() => {
    const errs: Record<string, string> = {};
    for (const q of clientState.questions) {
      if (q.answer_type !== "number") continue;
      const raw = editableAnswers[q.answer_key];
      if (raw === null || raw === undefined || raw === "") continue;
      const valueStr = String(raw);
      const dp = q.decimal_places ?? 0;
      const dot = valueStr.indexOf(".");
      const decimals = dot === -1 ? 0 : valueStr.length - dot - 1;
      if (decimals > dp) {
        errs[q.answer_key] =
          dp === 0
            ? "Please enter a whole number."
            : `Please enter a number with at most ${dp} decimal ${dp === 1 ? "place" : "places"}.`;
      }
    }
    return errs;
  }, [clientState.questions, editableAnswers]);

  const hasPrecisionError = Object.keys(numberPrecisionErrors).length > 0;

  async function handleContinue() {
    setScreenError(null);
    setPhotoError(null);
    setIsSubmitting(true);
    try {
      // Number answers are held as strings in editableAnswers (so the input and
      // the precision check see exactly what was typed). Convert them to JSON
      // numbers on the wire here; an empty number field becomes null. All other
      // answers pass through unchanged.
      const numberKeys = new Set(
        clientState.questions
          .filter((q) => q.answer_type === "number")
          .map((q) => q.answer_key)
      );
      const answersPayload: Record<string, boolean | string | number | null> = {};
      for (const [k, v] of Object.entries(editableAnswers)) {
        if (!numberKeys.has(k)) {
          answersPayload[k] = v;
        } else if (v === null || v === undefined || v === "") {
          answersPayload[k] = null;
        } else {
          answersPayload[k] = Number(v);
        }
      }

      const payload: ClientAnswerReturn = {
        runtime_id: runtimeId,
        base_version: version,
        answers: answersPayload,
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
    // Reset the input so the same file can be re-selected after removal.
    if (fileInputRef.current) fileInputRef.current.value = "";

    if (incoming.length === 0) return;

    // Per-file type and size checks.
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

    // Tier-conditional count check.
    // photoTier is guaranteed to be set before the file input is rendered,
    // but we check defensively here in case of unexpected state.
    const maxCount = photoTier ? TIER_MAX_COUNT[photoTier] : 1;
    if (photos.length + incoming.length > maxCount) {
      const noun = maxCount === 1 ? "photo" : "photos";
      setPhotoError(
        `You can upload a maximum of ${maxCount} ${noun} for this type of submission. ` +
        `You currently have ${photos.length}.`
      );
      return;
    }

    // Combined size check.
    const existingBytes = photos.reduce((sum, p) => sum + p.file.size, 0);
    const incomingBytes = incoming.reduce((sum, f) => sum + f.size, 0);
    if (existingBytes + incomingBytes > MAX_TOTAL_SIZE_BYTES) {
      const limitMB = (MAX_TOTAL_SIZE_BYTES / 1_048_576).toFixed(0);
      setPhotoError(
        `The total size of all photos cannot exceed ${limitMB} MB. Please remove a photo or choose smaller files.`
      );
      return;
    }

    // All checks passed — create PhotoAttachment objects and merge.
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

  function handleTierChange(tier: PhotoTier) {
    // If switching tier after photos have been added, clear the photos to
    // avoid a situation where the count constraint for the new tier is
    // violated silently by existing attachments.
    if (photos.length > 0) {
      photos.forEach((p) => URL.revokeObjectURL(p.previewUrl));
      onPhotosChange([]);
      setPhotoError(null);
    }
    onPhotoTierChange(tier);
  }

  const totalBytes = photos.reduce((sum, p) => sum + p.file.size, 0);
  const totalMB = (totalBytes / 1_048_576).toFixed(1);
  const limitMB = (MAX_TOTAL_SIZE_BYTES / 1_048_576).toFixed(0);
  const hasErrors = !!(screenError || photoError);

  // Derive hint text from the selected tier.
  function photoHintText(): string {
    if (photoTier === "high") {
      return "1 photo maximum. JPEG or PNG.";
    }
    if (photoTier === "standard") {
      return `Up to ${TIER_MAX_COUNT.standard} photos. JPEG or PNG.`;
    }
    return "Select a quality option above to add photos.";
  }

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

            if (q.answer_type === "number") {
              const raw = editableAnswers[q.answer_key];
              const valueStr =
                raw === null || raw === undefined ? "" : String(raw);
              const dp = q.decimal_places ?? 0;
              const step = dp > 0 ? `0.${"0".repeat(Math.max(0, dp - 1))}1` : "1";
              const precisionError = numberPrecisionErrors[q.answer_key];
              const numeric = valueStr === "" ? NaN : Number(valueStr);
              // Non-blocking out-of-range notice: shown only when the question
              // authored range_warning_text and the value is outside min/max.
              // It never disables Continue; that is solely the precision gate.
              const showRangeNotice =
                q.range_warning_text != null &&
                valueStr !== "" &&
                !Number.isNaN(numeric) &&
                ((q.min != null && numeric < q.min) ||
                  (q.max != null && numeric > q.max));

              return (
                <div
                  key={q.answer_key}
                  className={`field ${precisionError ? "has-error" : ""}`}
                >
                  <label htmlFor={inputId}>
                    {q.question_text}{" "}
                    {!q.required && (
                      <span className="field-label-optional">(optional)</span>
                    )}
                  </label>

                  <input
                    id={inputId}
                    type="number"
                    inputMode="decimal"
                    step={step}
                    min={q.min}
                    max={q.max}
                    aria-invalid={!!precisionError}
                    value={valueStr}
                    onChange={(e) => {
                      const next = e.target.value;
                      onAnswersChange({
                        ...editableAnswers,
                        [q.answer_key]: next === "" ? null : next,
                      });
                      if (screenError) setScreenError(null);
                    }}
                  />

                  {precisionError && <InlineError message={precisionError} />}

                  {showRangeNotice && (
                    <div
                      className="alert alert-info"
                      style={{ marginTop: "var(--space-sm)", padding: "8px 12px" }}
                    >
                      <p style={{ margin: 0, fontSize: "14px" }}>
                        {q.range_warning_text}
                      </p>
                    </div>
                  )}
                </div>
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
            <label>
              Photos{" "}
              <span className="field-label-optional">(optional)</span>
            </label>

            {/* Tier selection — shown always; file input appears only after selection */}
            <fieldset className="photo-tier-fieldset">
              <legend className="sr-only">Photo quality</legend>

              <label className={`selection-card ${photoTier === "high" ? "selected" : ""}`}>
                <input
                  type="radio"
                  name="photo-tier"
                  value="high"
                  checked={photoTier === "high"}
                  onChange={() => handleTierChange("high")}
                />
                <span className="selection-label">
                  High quality — 1 photo maximum. Recommended for skin lesions and moles.
                </span>
              </label>

              <label className={`selection-card ${photoTier === "standard" ? "selected" : ""}`}>
                <input
                  type="radio"
                  name="photo-tier"
                  value="standard"
                  checked={photoTier === "standard"}
                  onChange={() => handleTierChange("standard")}
                />
                <span className="selection-label">
                  Standard quality — up to 5 photos. Recommended for documents, letters, or general photos.
                </span>
              </label>
            </fieldset>

            {/* Guide link — shown once a tier is selected */}
            {photoTier !== null && (
              <button
                type="button"
                className="guide-link"
                onClick={() => setIsGuideOpen(true)}
              >
                How to take a good photo
              </button>
            )}

            {/* File input — only shown once a tier is selected */}
            {photoTier !== null && (
              <>
                <p id="photo-upload-hint" className="field-hint">
                  {photoHintText()}
                </p>

                <input
                  id="photo-upload"
                  ref={fileInputRef}
                  type="file"
                  accept="image/jpeg,image/png"
                  // Only allow multi-select for standard tier. Removing the
                  // multiple attribute prevents the OS picker from allowing
                  // more than one file, which is clearer than a post-selection error.
                  multiple={photoTier === "standard"}
                  aria-describedby="photo-upload-hint"
                  aria-invalid={!!photoError}
                  onChange={handleFileChange}
                  style={{ display: "block", marginTop: "var(--space-sm)", marginBottom: "var(--space-sm)" }}
                />
              </>
            )}

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
            disabled={!allRequiredAnswered || hasPrecisionError || isSubmitting}
            onClick={handleContinue}
          >
            {isSubmitting ? "Please wait\u2026" : "Review answers"}
          </button>
        </div>
      </form>

      {/* Photo guide modal */}
      {isGuideOpen && (
        <div
          className="modal-overlay"
          onClick={() => setIsGuideOpen(false)}
          role="dialog"
          aria-modal="true"
          aria-label="How to take a good photo"
        >
          {/* Stop clicks inside the modal from closing it via the overlay handler */}
          <div
            className="modal-panel"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              ref={guideCloseRef}
              type="button"
              className="modal-close"
              aria-label="Close guidance"
              onClick={() => setIsGuideOpen(false)}
            >
              &times;
            </button>

            <h2 className="modal-title">Taking a good photo</h2>

            <ul className="modal-guide-list">
              <li>Take the photo in a well-lit area</li>
              <li>
                For a close-up, hold the camera at least 15cm (6 inches) from
                the skin or the image will be blurry
              </li>
              <li>
                Tap the screen to focus on the area of interest rather than
                the background
              </li>
            </ul>

            <p className="modal-guide-subheading">For best results:</p>
            <ul className="modal-guide-list">
              <li>Ask someone else to take the photo for you</li>
              <li>Rest the phone on a stable surface</li>
              <li>Use the 3-second countdown timer if available</li>
            </ul>

            <img
              src="/photo-guide.jpg"
              alt="Example of a well-lit, clearly focused close-up photo"
              className="modal-guide-image"
            />

            <div className="modal-footer">
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => setIsGuideOpen(false)}
              >
                Got it
              </button>
            </div>
          </div>
        </div>
      )}
    </PageShell>
  );
}
/**
 * SignpostingEditor.tsx — Quill-based rich text editor for signposting content.
 *
 * Quill is an imperative, DOM-mutating library. It cannot be managed via
 * React state. The pattern here is:
 *   - A ref holds the DOM node that Quill mounts into (editorDivRef)
 *   - A ref holds the Quill instance itself (quillRef)
 *   - Quill is instantiated once in useEffect on mount
 *   - Content loading and event listeners are set up in a separate
 *     useEffect that runs after Quill is ready
 *
 * IMPORTANT: key={selectedId} on this component in EditorView forces a
 * full React remount every time the condition changes. This means Quill is
 * destroyed and recreated from scratch on every switch. This is intentional
 * — it avoids complex re-initialisation logic and keeps the component
 * simple. Do not remove key={selectedId} to optimise performance without
 * first understanding this dependency.
 *
 * Authentication: requests use the HttpOnly session cookie automatically.
 * No token is passed. If a request returns 401 (AuthError), onAuthError
 * is called and App transitions back to LoginView.
 */

import { useEffect, useRef, useState } from "react";
import Quill from "quill";
import DOMPurify from "dompurify";
import { fetchSignposting, putSignposting, AuthError } from "../api";
import { MAX_SIGNPOSTING_LENGTH, SIGNPOSTING_PURIFY_CONFIG } from "../../../src/constants";
import type { SaveStatus } from "../types";

interface Props {
  conditionId: string;
  onUnsavedChange: (hasChanges: boolean) => void;
  onAuthError: () => void;
}

export default function SignpostingEditor({
  conditionId,
  onUnsavedChange,
  onAuthError,
}: Props) {
  const editorDivRef = useRef<HTMLDivElement>(null);
  const quillRef = useRef<Quill | null>(null);

  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [saveStatus, setSaveStatus] = useState<SaveStatus | null>(null);
  const [hasUnsaved, setHasUnsaved] = useState(false);
  const [charCount, setCharCount] = useState(0);

  // Step 1: instantiate Quill once after the component mounts.
  useEffect(() => {
    if (!editorDivRef.current) return;

    const quill = new Quill(editorDivRef.current, {
      theme: "snow",
      placeholder: "Add information for patients here…",
      modules: {
        toolbar: [["bold", "italic", "link"], [{ list: "bullet" }]],
        keyboard: {
          bindings: {
            tab: false,
          },
        },
      },
    });

    quillRef.current = quill;

    return () => {
      quillRef.current = null;
    };
  }, []);

  // Step 2: once Quill exists, load content and set up change detection.
  useEffect(() => {
    if (!quillRef.current) return;

    const quill = quillRef.current;
    let cancelled = false;

    async function loadContent() {
      setIsLoading(true);
      setLoadError(null);

      try {
        const savedHtml = await fetchSignposting(conditionId);

        if (cancelled) return;

        if (savedHtml) {
          quill.clipboard.dangerouslyPasteHTML(savedHtml);
        }

        const baseline = quill.getSemanticHTML();
        setCharCount(baseline.length);

        quill.on("text-change", () => {
          const html = quill.getSemanticHTML();
          const changed = html !== baseline;
          setHasUnsaved(changed);
          onUnsavedChange(changed);
          setCharCount(html.length);
        });
      } catch (err) {
        if (cancelled) return;
        if (err instanceof AuthError) {
          onAuthError();
          return;
        }
        setLoadError(err instanceof Error ? err.message : "Unknown error");
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }

    loadContent();

    return () => {
      cancelled = true;
      quill.off("text-change");
    };
  }, [conditionId, onUnsavedChange, onAuthError]);

  async function handleSave() {
    const quill = quillRef.current;
    if (!quill) return;

    const rawHtml = quill.getSemanticHTML();
    if (rawHtml.length > MAX_SIGNPOSTING_LENGTH) {
      setSaveStatus({
        type: "error",
        text: `Save failed: content is ${rawHtml.length} characters, which exceeds the ${MAX_SIGNPOSTING_LENGTH} character limit`,
      });
      return;
    }

    setIsSaving(true);
    setSaveStatus(null);

    try {
      const sanitisedHtml = DOMPurify.sanitize(rawHtml, SIGNPOSTING_PURIFY_CONFIG);
      const savedHtml = await putSignposting(conditionId, sanitisedHtml);

      if (savedHtml) {
        quill.off("text-change");
        quill.clipboard.dangerouslyPasteHTML(savedHtml);

        const resyncedBaseline = quill.getSemanticHTML();
        setCharCount(resyncedBaseline.length);
        quill.on("text-change", () => {
          const html = quill.getSemanticHTML();
          const changed = html !== resyncedBaseline;
          setHasUnsaved(changed);
          onUnsavedChange(changed);
          setCharCount(html.length);
        });
      } else {
        quill.off("text-change");
        quill.setText("");

        const emptyBaseline = quill.getSemanticHTML();
        setCharCount(emptyBaseline.length);
        quill.on("text-change", () => {
          const html = quill.getSemanticHTML();
          const changed = html !== emptyBaseline;
          setHasUnsaved(changed);
          onUnsavedChange(changed);
          setCharCount(html.length);
        });
      }

      setHasUnsaved(false);
      onUnsavedChange(false);
      setSaveStatus({ type: "success", text: "Saved" });
    } catch (err) {
      if (err instanceof AuthError) {
        onAuthError();
        return;
      }
      const isNetworkError =
        err instanceof TypeError &&
        err.message.toLowerCase().includes("fetch");
      const msg = isNetworkError
        ? "Save failed: could not reach server"
        : `Save failed: ${err instanceof Error ? err.message : "Unknown error"}`;
      setSaveStatus({ type: "error", text: msg });
    } finally {
      setIsSaving(false);
    }
  }

  if (loadError) {
    return (
      <div className="alert alert-error">
        Could not load signposting: {loadError}
      </div>
    );
  }

  return (
    <div>
      {isLoading && (
        <div className="loading-row">
          <span className="spinner dark" />
          Loading…
        </div>
      )}

      <div style={{ display: isLoading ? "none" : "block" }}>
        <div className="quill-wrapper">
          <div ref={editorDivRef} />
        </div>

        <div
          className={`char-counter${charCount > MAX_SIGNPOSTING_LENGTH ? " over-limit" : ""}`}
        >
          {charCount} / {MAX_SIGNPOSTING_LENGTH} characters
        </div>

        <div className="editor-actions">
          <button
            className="btn btn-primary"
            onClick={handleSave}
            disabled={isSaving || charCount > MAX_SIGNPOSTING_LENGTH}
          >
            {isSaving ? (
              <>
                <span className="spinner" />
                Saving…
              </>
            ) : (
              "Save"
            )}
          </button>
          {saveStatus && (
            <span className={`save-status ${saveStatus.type}`}>
              {saveStatus.text}
            </span>
          )}
        </div>

        {hasUnsaved && !saveStatus && (
          <div className="alert alert-warning" style={{ marginTop: 14 }}>
            You have unsaved changes.
          </div>
        )}
      </div>
    </div>
  );
}
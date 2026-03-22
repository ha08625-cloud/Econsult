/**
 * PracticeSettingsTab.tsx — practice contact details editor.
 *
 * Fetches the current practice record on mount and allows the admin to
 * update the email address.
 *
 * State machine:
 * - "loading"  — initial fetch in progress
 * - "ready"    — fetch succeeded; form is interactive
 * - "error"    — initial fetch failed; shows error message with no form
 *
 * Save state is separate from load state and uses a plain string
 * discriminant rather than a union type, consistent with SaveStatus
 * elsewhere in the admin UI.
 *
 * This component is conditionally rendered by EditorView (destroyed and
 * recreated on each tab switch), so it always performs a fresh fetch on
 * entry. This is intentional — practice details are not expected to change
 * frequently and stale-on-return is not a concern here.
 *
 * No unsaved-change guard is needed: the input is a single text field and
 * any partially typed value is low-stakes to lose on tab switch.
 */

import { useEffect, useState } from "react";
import { getPractice, updatePracticeEmail } from "./api";
import type { PracticeDetails } from "./api";

interface Props {
  token: string;
}

type LoadState = "loading" | "ready" | "error";

export default function PracticeSettingsTab({ token }: Props) {
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [loadError, setLoadError] = useState<string | null>(null);

  const [practice, setPractice] = useState<PracticeDetails | null>(null);
  const [emailInput, setEmailInput] = useState("");

  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saveSuccess, setSaveSuccess] = useState(false);

  useEffect(() => {
    let cancelled = false;

    getPractice(token)
      .then((data) => {
        if (cancelled) return;
        setPractice(data);
        setEmailInput(data.email);
        setLoadState("ready");
      })
      .catch((err) => {
        if (cancelled) return;
        setLoadError(err instanceof Error ? err.message : "Failed to load practice details.");
        setLoadState("error");
      });

    return () => {
      cancelled = true;
    };
  }, [token]);

  async function handleSave() {
    if (!practice) return;

    setSaveError(null);
    setSaveSuccess(false);
    setIsSaving(true);

    try {
      const updated = await updatePracticeEmail(token, emailInput.trim());
      setPractice(updated);
      setEmailInput(updated.email);
      setSaveSuccess(true);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Save failed.");
    } finally {
      setIsSaving(false);
    }
  }

  // -------------------------------------------------------------------------
  // Render: loading
  // -------------------------------------------------------------------------

  if (loadState === "loading") {
    return (
      <div className="card">
        <p className="card-subtitle">Loading practice details...</p>
      </div>
    );
  }

  // -------------------------------------------------------------------------
  // Render: load error
  // -------------------------------------------------------------------------

  if (loadState === "error") {
    return (
      <div className="card">
        <p className="card-title">Practice settings</p>
        <p className="error-message">{loadError}</p>
      </div>
    );
  }

  // -------------------------------------------------------------------------
  // Render: ready
  // -------------------------------------------------------------------------

  return (
    <div className="card">
      <p className="card-title">Practice settings</p>
      <p className="card-subtitle">Practice contact details and email configuration.</p>

      <hr className="divider" />

      <div className="field-row">
        <span className="field-label">Practice name</span>
        <span className="field-value">{practice!.name}</span>
      </div>

      <div className="field-row">
        <span className="field-label">Practice ID</span>
        <span className="field-value field-value--muted">{practice!.practice_id}</span>
      </div>

      <hr className="divider" />

      <p className="section-label">Contact email</p>
      <p className="card-subtitle">
        Clinical output from form submissions is sent to this address.
      </p>

      <div className="input-row">
        <input
          type="email"
          className="text-input"
          value={emailInput}
          onChange={(e) => {
            setEmailInput(e.target.value);
            setSaveSuccess(false);
            setSaveError(null);
          }}
          disabled={isSaving}
          aria-label="Contact email address"
        />
        <button
          className="btn-primary"
          onClick={handleSave}
          disabled={isSaving || emailInput.trim() === ""}
        >
          {isSaving ? "Saving..." : "Save"}
        </button>
      </div>

      {saveSuccess && (
        <p className="save-success">Email address updated.</p>
      )}

      {saveError && (
        <p className="error-message">{saveError}</p>
      )}
    </div>
  );
}
/**
 * PracticeSettingsTab.tsx — practice contact details and doctor list editor.
 *
 * Contains two independent sections:
 *
 * 1. Contact email — fetches and updates the practice email address.
 * 2. Doctor list — fetches and replaces the ordered list of doctor names
 *    used to populate the patient-facing dropdown on the Contact screen.
 *
 * Both sections share a single load state. Both fetches are issued in
 * parallel on mount and the component enters "ready" only when both
 * succeed. If either fails, the component enters "error".
 *
 * Save state for each section is independent.
 *
 * Authentication: requests use the HttpOnly session cookie automatically.
 * No token is passed. If a request returns 401 (AuthError), onAuthError
 * is called and App transitions back to LoginView.
 *
 * This component is conditionally rendered by EditorView (destroyed and
 * recreated on each tab switch), so it always performs a fresh fetch on
 * entry. This is intentional.
 */

import { useEffect, useState } from "react";
import { getPractice, updatePracticeEmail, getDoctors, putDoctors, AuthError } from "../api";
import type { PracticeDetails } from "../api";

interface Props {
  onAuthError: () => void;
}

type LoadState = "loading" | "ready" | "error";
type SaveStatus = "idle" | "saving" | "success" | "error";

export default function PracticeSettingsTab({ onAuthError }: Props) {
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [loadError, setLoadError] = useState<string | null>(null);

  const [practice, setPractice] = useState<PracticeDetails | null>(null);
  const [emailInput, setEmailInput] = useState("");
  const [emailSaveStatus, setEmailSaveStatus] = useState<SaveStatus>("idle");
  const [emailSaveError, setEmailSaveError] = useState<string | null>(null);

  const [doctors, setDoctors] = useState<string[]>([]);
  const [addInput, setAddInput] = useState("");
  const [addError, setAddError] = useState<string | null>(null);
  const [doctorSaveStatus, setDoctorSaveStatus] = useState<SaveStatus>("idle");
  const [doctorSaveError, setDoctorSaveError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    Promise.all([getPractice(), getDoctors()])
      .then(([practiceData, doctorData]) => {
        if (cancelled) return;
        setPractice(practiceData);
        setEmailInput(practiceData.email);
        setDoctors(doctorData);
        setLoadState("ready");
      })
      .catch((err) => {
        if (cancelled) return;
        if (err instanceof AuthError) { onAuthError(); return; }
        setLoadError(err instanceof Error ? err.message : "Failed to load practice settings.");
        setLoadState("error");
      });

    return () => {
      cancelled = true;
    };
  }, [onAuthError]);

  async function handleEmailSave() {
    if (!practice) return;

    setEmailSaveError(null);
    setEmailSaveStatus("saving");

    try {
      const updated = await updatePracticeEmail(emailInput.trim());
      setPractice(updated);
      setEmailInput(updated.email);
      setEmailSaveStatus("success");
    } catch (err) {
      if (err instanceof AuthError) { onAuthError(); return; }
      setEmailSaveError(err instanceof Error ? err.message : "Save failed.");
      setEmailSaveStatus("error");
    }
  }

  function handleMoveUp(index: number) {
    if (index === 0) return;
    const updated = [...doctors];
    [updated[index - 1], updated[index]] = [updated[index], updated[index - 1]];
    setDoctors(updated);
    setDoctorSaveStatus("idle");
  }

  function handleMoveDown(index: number) {
    if (index === doctors.length - 1) return;
    const updated = [...doctors];
    [updated[index], updated[index + 1]] = [updated[index + 1], updated[index]];
    setDoctors(updated);
    setDoctorSaveStatus("idle");
  }

  function handleDelete(index: number) {
    setDoctors(doctors.filter((_, i) => i !== index));
    setDoctorSaveStatus("idle");
  }

  function handleAdd() {
    const name = addInput.trim();
    if (!name) return;
    if (doctors.some((d) => d.trim().toLowerCase() === name.toLowerCase())) {
      setAddError(`"${name}" is already on the list.`);
      return;
    }
    setAddError(null);
    setDoctors([...doctors, name]);
    setAddInput("");
    setDoctorSaveStatus("idle");
  }

  function handleAddKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter") {
      e.preventDefault();
      handleAdd();
    }
  }

  async function handleDoctorSave() {
    setDoctorSaveError(null);
    setDoctorSaveStatus("saving");

    try {
      const saved = await putDoctors(doctors);
      setDoctors(saved);
      setDoctorSaveStatus("success");
    } catch (err) {
      if (err instanceof AuthError) { onAuthError(); return; }
      setDoctorSaveError(err instanceof Error ? err.message : "Save failed.");
      setDoctorSaveStatus("error");
    }
  }

  if (loadState === "loading") {
    return (
      <div className="card">
        <p className="card-subtitle">Loading practice details...</p>
      </div>
    );
  }

  if (loadState === "error") {
    return (
      <div className="card">
        <p className="card-title">Practice settings</p>
        <p className="error-message">{loadError}</p>
      </div>
    );
  }

  return (
    <div className="card">
      <p className="card-title">Practice settings</p>
      <p className="card-subtitle">Practice contact details and configuration.</p>

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
            setEmailSaveStatus("idle");
            setEmailSaveError(null);
          }}
          disabled={emailSaveStatus === "saving"}
          aria-label="Contact email address"
        />
        <button
          className="btn-primary"
          onClick={handleEmailSave}
          disabled={emailSaveStatus === "saving" || emailInput.trim() === ""}
        >
          {emailSaveStatus === "saving" ? "Saving..." : "Save"}
        </button>
      </div>

      {emailSaveStatus === "success" && (
        <p className="save-success">Email address updated.</p>
      )}

      {emailSaveStatus === "error" && emailSaveError && (
        <p className="error-message">{emailSaveError}</p>
      )}

      <hr className="divider" />

      <p className="section-label">Doctor list</p>
      <p className="card-subtitle">
        Configure the list of doctors shown to patients on the contact screen.
        Patients will be able to select their preferred doctor from this list,
        or enter a name manually. Leave this list empty to show only a free text
        field.
      </p>

      {doctors.length === 0 ? (
        <div className="empty-state" style={{ marginBottom: "16px" }}>
          No doctors configured. Add a name below.
        </div>
      ) : (
        <ul
          style={{
            listStyle: "none",
            padding: 0,
            margin: "0 0 16px 0",
            border: "1px solid var(--border)",
            borderRadius: "var(--btn-radius)",
            overflow: "hidden",
          }}
        >
          {doctors.map((name, index) => (
            <li
              key={index}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "8px",
                padding: "10px 12px",
                borderBottom: index < doctors.length - 1 ? "1px solid var(--border)" : "none",
                background: "var(--surface)",
                fontSize: "14px",
              }}
            >
              <span style={{ flex: 1 }}>{name}</span>
              <button
                className="btn btn-ghost"
                onClick={() => handleMoveUp(index)}
                disabled={index === 0}
                aria-label={`Move ${name} up`}
                title="Move up"
                style={{ padding: "2px 6px" }}
              >
                ↑
              </button>
              <button
                className="btn btn-ghost"
                onClick={() => handleMoveDown(index)}
                disabled={index === doctors.length - 1}
                aria-label={`Move ${name} down`}
                title="Move down"
                style={{ padding: "2px 6px" }}
              >
                ↓
              </button>
              <button
                className="btn btn-ghost"
                onClick={() => handleDelete(index)}
                aria-label={`Remove ${name}`}
                title="Remove"
                style={{ padding: "2px 6px", color: "var(--danger)" }}
              >
                ✕
              </button>
            </li>
          ))}
        </ul>
      )}

      <div className="input-row" style={{ marginBottom: "16px" }}>
        <input
          type="text"
          className="text-input"
          placeholder="e.g. Dr Smith"
          value={addInput}
          onChange={(e) => {
            setAddInput(e.target.value);
            setAddError(null);
          }}
          onKeyDown={handleAddKeyDown}
          aria-label="New doctor name"
        />
        <button
          className="btn-outline btn"
          onClick={handleAdd}
          disabled={addInput.trim() === ""}
        >
          Add
        </button>
      </div>

      {addError && (
        <p className="error-message" style={{ marginTop: "-8px", marginBottom: "16px" }}>{addError}</p>
      )}

      <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
        <button
          className="btn-primary btn"
          onClick={handleDoctorSave}
          disabled={doctorSaveStatus === "saving"}
        >
          {doctorSaveStatus === "saving" ? "Saving..." : "Save doctor list"}
        </button>

        {doctorSaveStatus === "success" && (
          <p className="save-success" style={{ margin: 0 }}>Doctor list saved.</p>
        )}
      </div>

      {doctorSaveStatus === "error" && doctorSaveError && (
        <p className="error-message" style={{ marginTop: "8px" }}>{doctorSaveError}</p>
      )}
    </div>
  );
}
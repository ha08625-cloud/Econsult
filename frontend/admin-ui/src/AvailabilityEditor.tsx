/**
 * AvailabilityEditor.tsx — Availability configuration card.
 *
 * Fetches the current config on mount. Provides:
 * - Enable/disable toggle (is_active)
 * - Weekday checkboxes (Mon–Sun)
 * - Open time and close time inputs
 * - Closed message textarea
 * - Save button calling PUT /admin/availability
 *
 * If is_active is true and no days are selected, a confirmation dialog
 * is shown before saving.
 */

import { useEffect, useState } from "react";
import { fetchAvailability, putAvailability } from "./api";
import type { SaveStatus } from "./types";

interface Props {
  token: string;
}

const ALL_DAYS = [
  { key: "mon", label: "Mon" },
  { key: "tue", label: "Tue" },
  { key: "wed", label: "Wed" },
  { key: "thu", label: "Thu" },
  { key: "fri", label: "Fri" },
  { key: "sat", label: "Sat" },
  { key: "sun", label: "Sun" },
] as const;

export default function AvailabilityEditor({ token }: Props) {
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [saveStatus, setSaveStatus] = useState<SaveStatus | null>(null);

  // Form state
  const [isActive, setIsActive] = useState(false);
  const [weeklyOpenDays, setWeeklyOpenDays] = useState<string[]>([]);
  const [openTime, setOpenTime] = useState("08:00");
  const [closeTime, setCloseTime] = useState("18:30");
  const [closedMessage, setClosedMessage] = useState("");

  // Load config on mount
  useEffect(() => {
    let cancelled = false;

    async function load() {
      setIsLoading(true);
      setLoadError(null);
      try {
        const config = await fetchAvailability(token);
        if (cancelled) return;
        setIsActive(config.is_active);
        setWeeklyOpenDays(config.weekly_open_days);
        setOpenTime(config.open_time);
        setCloseTime(config.close_time);
        setClosedMessage(config.closed_message ?? "");
      } catch (err) {
        if (!cancelled) {
          setLoadError(err instanceof Error ? err.message : "Unknown error");
        }
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }

    load();
    return () => { cancelled = true; };
  }, [token]);

  function toggleDay(day: string) {
    setWeeklyOpenDays((prev) =>
      prev.includes(day) ? prev.filter((d) => d !== day) : [...prev, day]
    );
    setSaveStatus(null);
  }

  async function handleSave() {
    // Empty-days confirmation dialog
    if (isActive && weeklyOpenDays.length === 0) {
      const confirmed = window.confirm(
        "No days are selected. Saving this configuration will close the form to patients on every day of the week. Are you sure?"
      );
      if (!confirmed) return;
    }

    setIsSaving(true);
    setSaveStatus(null);

    try {
      const updated = await putAvailability(token, {
        is_active: isActive,
        weekly_open_days: weeklyOpenDays,
        open_time: openTime,
        close_time: closeTime,
        closed_message: closedMessage.trim() || null,
      });

      // Sync form state with what the server returned
      setIsActive(updated.is_active);
      setWeeklyOpenDays(updated.weekly_open_days);
      setOpenTime(updated.open_time);
      setCloseTime(updated.close_time);
      setClosedMessage(updated.closed_message ?? "");
      setSaveStatus({ type: "success", text: "Saved" });
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Unknown error";
      setSaveStatus({ type: "error", text: msg });
    } finally {
      setIsSaving(false);
    }
  }

  if (loadError) {
    return (
      <div className="card">
        <p className="card-title">Opening hours</p>
        <div className="alert alert-error">
          Could not load availability settings: {loadError}
        </div>
      </div>
    );
  }

  return (
    <div className="card">
      <p className="card-title">Opening hours</p>
      <p className="card-subtitle">
        Control when the online consultation form is available to patients.
      </p>

      {isLoading ? (
        <div className="loading-row">
          <span className="spinner dark" />
          Loading...
        </div>
      ) : (
        <>
          {/* Enable/disable toggle */}
          <div style={{ marginBottom: "24px" }}>
            <label
              style={{
                display: "flex",
                alignItems: "center",
                gap: "10px",
                cursor: "pointer",
                textTransform: "none",
                letterSpacing: "normal",
                fontSize: "15px",
                fontWeight: 400,
                color: "var(--text)",
              }}
            >
              <input
                type="checkbox"
                checked={isActive}
                onChange={(e) => {
                  setIsActive(e.target.checked);
                  setSaveStatus(null);
                }}
                style={{ width: "18px", height: "18px" }}
              />
              Enforce opening hours
            </label>
            <p
              style={{
                fontSize: "13px",
                color: "var(--text-muted)",
                marginTop: "4px",
                marginLeft: "28px",
              }}
            >
              {isActive
                ? "The form will only be available during the hours below."
                : "The form is available at all times. Opening hours are not enforced."}
            </p>
          </div>

          {/* Settings — only shown when active */}
          {isActive && (
            <>
              <hr className="divider" />

              {/* Weekday checkboxes */}
              <div style={{ marginBottom: "20px" }}>
                <p className="section-label" style={{ marginTop: 0 }}>
                  Open days
                </p>
                <div style={{ display: "flex", gap: "6px", flexWrap: "wrap" }}>
                  {ALL_DAYS.map((d) => {
                    const selected = weeklyOpenDays.includes(d.key);
                    return (
                      <button
                        key={d.key}
                        type="button"
                        onClick={() => toggleDay(d.key)}
                        className={selected ? "btn btn-primary" : "btn btn-outline"}
                        style={{
                          minWidth: "52px",
                          justifyContent: "center",
                        }}
                      >
                        {d.label}
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Time inputs */}
              <div
                style={{
                  display: "flex",
                  gap: "16px",
                  marginBottom: "20px",
                }}
              >
                <div style={{ flex: 1 }}>
                  <label htmlFor="avail-open-time">Open time</label>
                  <input
                    id="avail-open-time"
                    type="time"
                    value={openTime}
                    onChange={(e) => {
                      setOpenTime(e.target.value);
                      setSaveStatus(null);
                    }}
                    style={{
                      width: "100%",
                      padding: "9px 12px",
                      border: "1px solid var(--border)",
                      borderRadius: "var(--btn-radius)",
                      fontFamily: "inherit",
                      fontSize: "15px",
                      color: "var(--text)",
                      background: "var(--surface)",
                    }}
                  />
                </div>
                <div style={{ flex: 1 }}>
                  <label htmlFor="avail-close-time">Close time</label>
                  <input
                    id="avail-close-time"
                    type="time"
                    value={closeTime}
                    onChange={(e) => {
                      setCloseTime(e.target.value);
                      setSaveStatus(null);
                    }}
                    style={{
                      width: "100%",
                      padding: "9px 12px",
                      border: "1px solid var(--border)",
                      borderRadius: "var(--btn-radius)",
                      fontFamily: "inherit",
                      fontSize: "15px",
                      color: "var(--text)",
                      background: "var(--surface)",
                    }}
                  />
                </div>
              </div>

              {/* Closed message */}
              <div style={{ marginBottom: "20px" }}>
                <label htmlFor="avail-closed-message">Closed message</label>
                <textarea
                  id="avail-closed-message"
                  value={closedMessage}
                  onChange={(e) => {
                    setClosedMessage(e.target.value);
                    setSaveStatus(null);
                  }}
                  rows={3}
                  placeholder="Message shown to patients when the form is closed"
                  style={{
                    width: "100%",
                    padding: "9px 12px",
                    border: "1px solid var(--border)",
                    borderRadius: "var(--btn-radius)",
                    fontFamily: "inherit",
                    fontSize: "15px",
                    color: "var(--text)",
                    background: "var(--surface)",
                    resize: "vertical",
                  }}
                />
                <p
                  style={{
                    fontSize: "13px",
                    color: "var(--text-muted)",
                    marginTop: "4px",
                  }}
                >
                  Optional. If left blank, patients will see a generic closure
                  notice.
                </p>
              </div>
            </>
          )}

          {/* Save button and status */}
          <div className="editor-actions">
            <button
              className="btn btn-primary"
              onClick={handleSave}
              disabled={isSaving}
            >
              {isSaving ? (
                <>
                  <span className="spinner" />
                  Saving...
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
        </>
      )}
    </div>
  );
}

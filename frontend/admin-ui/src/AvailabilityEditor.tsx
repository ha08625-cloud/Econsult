/**
 * AvailabilityEditor.tsx — Availability configuration card.
 *
 * Fetches the current config on mount. Provides:
 * - Enable/disable toggle (is_active)
 * - Weekday checkboxes (Mon–Sun)
 * - Open time and close time inputs
 * - Closed message textarea
 * - Save button calling PUT /admin/availability
 * - Override panel: force open / force closed with expiry
 * - Exceptions panel: per-date closures and custom hours
 *
 * If is_active is true and no days are selected, a confirmation dialog
 * is shown before saving.
 *
 * Override active check uses UTC comparison (Date.now() is UTC-safe).
 * Override expiry display uses Europe/London formatting via Intl.DateTimeFormat.
 *
 * Unsaved change tracking:
 * - onUnsavedChange is called whenever the five schedule fields (isActive,
 *   weeklyOpenDays, openTime, closeTime, closedMessage) differ from the
 *   last value applied by syncFormState.
 * - savedStateRef holds the last-known-clean values and is written
 *   synchronously inside syncFormState, which is the single reset point
 *   covering both initial load and post-save.
 * - weeklyOpenDays comparison uses sorted JSON.stringify to avoid false
 *   positives from array reference inequality.
 */

import { useEffect, useRef, useState } from "react";
import {
  fetchAvailability,
  putAvailability,
  postOverride,
  deleteOverride,
  fetchExceptions,
  putException,
  deleteException,
} from "./api";
import type { AvailabilityConfig, AvailabilityException, SaveStatus } from "./types";

interface Props {
  token: string;
  onUnsavedChange?: (hasChanges: boolean) => void;
}

interface SavedScheduleState {
  isActive: boolean;
  weeklyOpenDays: string[];
  openTime: string;
  closeTime: string;
  closedMessage: string;
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

/**
 * Format a UTC ISO timestamp in Europe/London local time for display.
 * During BST the UTC offset is +1, so displaying in UTC would show
 * the wrong time to a UK-based admin.
 */
function formatLondonTime(isoString: string): string {
  const date = new Date(isoString);
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: "Europe/London",
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
}

/**
 * Format a YYYY-MM-DD date string for display: "Mon 14 Jul 2025"
 */
function formatExceptionDate(dateStr: string): string {
  const date = new Date(dateStr + "T12:00:00"); // noon to avoid timezone shifts
  return new Intl.DateTimeFormat("en-GB", {
    weekday: "short",
    day: "numeric",
    month: "short",
    year: "numeric",
  }).format(date);
}

/**
 * Check whether an override is currently active.
 * Uses Date.now() which is UTC-safe. Local time must not be used.
 */
function isOverrideActive(config: AvailabilityConfig): boolean {
  return (
    config.override_status !== null &&
    config.override_expires_at !== null &&
    new Date(config.override_expires_at).getTime() > Date.now()
  );
}

/**
 * Build a default expiry datetime string for the override form.
 * Returns a local datetime string suitable for datetime-local input,
 * set to 2 hours from now rounded to nearest 15 minutes.
 */
function defaultExpiryLocal(): string {
  const d = new Date(Date.now() + 2 * 60 * 60 * 1000);
  // Round to nearest 15 minutes
  d.setMinutes(Math.ceil(d.getMinutes() / 15) * 15, 0, 0);
  // Format as YYYY-MM-DDTHH:MM for datetime-local input
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/**
 * Build a max expiry datetime string for the override form (24 hours ahead).
 */
function maxExpiryLocal(): string {
  const d = new Date(Date.now() + 24 * 60 * 60 * 1000);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/**
 * Get today's date in YYYY-MM-DD format for the date input min attribute.
 */
function todayDateString(): string {
  const d = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/**
 * Compare two day arrays by sorting both and comparing as JSON.
 * Required because array reference equality always returns false.
 */
function daysEqual(a: string[], b: string[]): boolean {
  return JSON.stringify([...a].sort()) === JSON.stringify([...b].sort());
}

export default function AvailabilityEditor({ token, onUnsavedChange }: Props) {
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [saveStatus, setSaveStatus] = useState<SaveStatus | null>(null);

  // Full config from server (includes override fields)
  const [config, setConfig] = useState<AvailabilityConfig | null>(null);

  // Form state for schedule editing
  const [isActive, setIsActive] = useState(false);
  const [weeklyOpenDays, setWeeklyOpenDays] = useState<string[]>([]);
  const [openTime, setOpenTime] = useState("08:00");
  const [closeTime, setCloseTime] = useState("18:30");
  const [closedMessage, setClosedMessage] = useState("");

  // Holds the last-known-clean schedule values (set by syncFormState).
  // Used to detect unsaved changes without triggering re-renders.
  const savedStateRef = useRef<SavedScheduleState | null>(null);

  // Override form state
  const [overrideFormOpen, setOverrideFormOpen] = useState(false);
  const [overrideFormStatus, setOverrideFormStatus] = useState<"open" | "closed">("closed");
  const [overrideFormExpiry, setOverrideFormExpiry] = useState(defaultExpiryLocal());
  const [overrideFormMessage, setOverrideFormMessage] = useState("");
  const [overrideError, setOverrideError] = useState<string | null>(null);
  const [isOverrideSubmitting, setIsOverrideSubmitting] = useState(false);

  // Exceptions state
  const [exceptions, setExceptions] = useState<AvailabilityException[]>([]);
  const [exceptionsLoading, setExceptionsLoading] = useState(false);
  const [exceptionsError, setExceptionsError] = useState<string | null>(null);
  const [exceptionFormOpen, setExceptionFormOpen] = useState(false);
  const [excFormDate, setExcFormDate] = useState("");
  const [excFormType, setExcFormType] = useState<"closed" | "custom_hours">("closed");
  const [excFormOpenTime, setExcFormOpenTime] = useState("09:00");
  const [excFormCloseTime, setExcFormCloseTime] = useState("13:00");
  const [excFormNote, setExcFormNote] = useState("");
  const [excFormError, setExcFormError] = useState<string | null>(null);
  const [excFormSubmitting, setExcFormSubmitting] = useState(false);
  const [excDeleting, setExcDeleting] = useState<string | null>(null);

  /**
   * Apply server config to local form state and reset the clean baseline.
   * This is the single point where server state becomes local state —
   * called on initial load and after every successful save or override change.
   */
  function syncFormState(cfg: AvailabilityConfig) {
    setConfig(cfg);
    setIsActive(cfg.is_active);
    setWeeklyOpenDays(cfg.weekly_open_days);
    setOpenTime(cfg.open_time);
    setCloseTime(cfg.close_time);
    setClosedMessage(cfg.closed_message ?? "");

    // Write the clean baseline synchronously before any async gap.
    savedStateRef.current = {
      isActive: cfg.is_active,
      weeklyOpenDays: cfg.weekly_open_days,
      openTime: cfg.open_time,
      closeTime: cfg.close_time,
      closedMessage: cfg.closed_message ?? "",
    };

    onUnsavedChange?.(false);
  }

  /**
   * Compare current form values against the saved baseline and notify
   * the parent if dirty state has changed.
   * Called after every change to the five schedule fields.
   */
  function checkDirty(
    currentIsActive: boolean,
    currentDays: string[],
    currentOpenTime: string,
    currentCloseTime: string,
    currentClosedMessage: string,
  ) {
    if (!savedStateRef.current) return;
    const s = savedStateRef.current;
    const dirty =
      currentIsActive !== s.isActive ||
      !daysEqual(currentDays, s.weeklyOpenDays) ||
      currentOpenTime !== s.openTime ||
      currentCloseTime !== s.closeTime ||
      currentClosedMessage !== s.closedMessage;
    onUnsavedChange?.(dirty);
  }

  // Load config on mount
  useEffect(() => {
    let cancelled = false;

    async function load() {
      setIsLoading(true);
      setLoadError(null);
      try {
        const cfg = await fetchAvailability(token);
        if (cancelled) return;
        syncFormState(cfg);
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

  // Load exceptions when isActive becomes true (or on mount if already active)
  useEffect(() => {
    if (!isActive) return;

    let cancelled = false;

    async function loadExceptions() {
      setExceptionsLoading(true);
      setExceptionsError(null);
      try {
        const exc = await fetchExceptions(token);
        if (!cancelled) setExceptions(exc);
      } catch (err) {
        if (!cancelled) {
          setExceptionsError(err instanceof Error ? err.message : "Unknown error");
        }
      } finally {
        if (!cancelled) setExceptionsLoading(false);
      }
    }

    loadExceptions();
    return () => { cancelled = true; };
  }, [token, isActive]);

  function toggleDay(day: string) {
    const newDays = weeklyOpenDays.includes(day)
      ? weeklyOpenDays.filter((d) => d !== day)
      : [...weeklyOpenDays, day];
    setWeeklyOpenDays(newDays);
    setSaveStatus(null);
    checkDirty(isActive, newDays, openTime, closeTime, closedMessage);
  }

  async function handleSave() {
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
      syncFormState(updated);
      setSaveStatus({ type: "success", text: "Saved" });
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Unknown error";
      setSaveStatus({ type: "error", text: msg });
    } finally {
      setIsSaving(false);
    }
  }

  // --- Override handlers ---

  function openOverrideForm(status: "open" | "closed") {
    setOverrideFormStatus(status);
    setOverrideFormExpiry(defaultExpiryLocal());
    setOverrideFormMessage("");
    setOverrideError(null);
    setOverrideFormOpen(true);
  }

  async function handleOverrideSubmit() {
    setIsOverrideSubmitting(true);
    setOverrideError(null);

    try {
      // Convert local datetime-local value to UTC ISO string.
      // The datetime-local input gives us a string without timezone info.
      // We construct a Date from it (which interprets it as local time)
      // and then call toISOString() to get UTC.
      const localDate = new Date(overrideFormExpiry);
      if (isNaN(localDate.getTime())) {
        setOverrideError("Please enter a valid date and time.");
        return;
      }
      const utcIso = localDate.toISOString();

      const updated = await postOverride(token, {
        status: overrideFormStatus,
        expires_at: utcIso,
        message: overrideFormMessage.trim() || null,
      });
      syncFormState(updated);
      setOverrideFormOpen(false);
    } catch (err) {
      setOverrideError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setIsOverrideSubmitting(false);
    }
  }

  async function handleClearOverride() {
    setIsOverrideSubmitting(true);
    setOverrideError(null);

    try {
      const updated = await deleteOverride(token);
      syncFormState(updated);
    } catch (err) {
      setOverrideError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setIsOverrideSubmitting(false);
    }
  }

  // --- Exception handlers ---

  function openExceptionForm() {
    setExcFormDate("");
    setExcFormType("closed");
    setExcFormOpenTime("09:00");
    setExcFormCloseTime("13:00");
    setExcFormNote("");
    setExcFormError(null);
    setExceptionFormOpen(true);
  }

  async function handleExceptionSubmit() {
    if (!excFormDate) {
      setExcFormError("Please select a date.");
      return;
    }

    setExcFormSubmitting(true);
    setExcFormError(null);

    try {
      await putException(token, excFormDate, {
        exception_type: excFormType,
        open_time: excFormType === "custom_hours" ? excFormOpenTime : null,
        close_time: excFormType === "custom_hours" ? excFormCloseTime : null,
        note: excFormNote.trim() || null,
      });
      // Reload exceptions list
      const updated = await fetchExceptions(token);
      setExceptions(updated);
      setExceptionFormOpen(false);
    } catch (err) {
      setExcFormError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setExcFormSubmitting(false);
    }
  }

  async function handleDeleteException(date: string) {
    setExcDeleting(date);
    try {
      await deleteException(token, date);
      setExceptions((prev) => prev.filter((e) => e.exception_date !== date));
    } catch (err) {
      // Show a brief alert — not worth a dedicated error state per row
      alert(err instanceof Error ? err.message : "Failed to delete exception");
    } finally {
      setExcDeleting(null);
    }
  }

  // --- Render ---

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

  const hasActiveOverride = config !== null && isOverrideActive(config);

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
                  const val = e.target.checked;
                  setIsActive(val);
                  setSaveStatus(null);
                  checkDirty(val, weeklyOpenDays, openTime, closeTime, closedMessage);
                }}
                style={{ width: "16px", height: "16px", cursor: "pointer" }}
              />
              Enable availability checking
            </label>
            <p style={{ fontSize: "13px", color: "var(--text-muted)", marginTop: "6px" }}>
              When disabled, the form is always accessible regardless of time or day.
            </p>
          </div>

          {isActive && (
            <>
              {/* Weekly schedule */}
              <div style={{ marginBottom: "20px" }}>
                <label>Open days</label>
                <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", marginTop: "6px" }}>
                  {ALL_DAYS.map(({ key, label }) => (
                    <label
                      key={key}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: "5px",
                        textTransform: "none",
                        letterSpacing: "normal",
                        fontSize: "14px",
                        fontWeight: 400,
                        color: "var(--text)",
                        cursor: "pointer",
                        padding: "5px 10px",
                        border: `1px solid ${weeklyOpenDays.includes(key) ? "var(--accent)" : "var(--border)"}`,
                        borderRadius: "var(--btn-radius)",
                        background: weeklyOpenDays.includes(key) ? "rgba(26,111,168,0.07)" : "var(--surface)",
                      }}
                    >
                      <input
                        type="checkbox"
                        checked={weeklyOpenDays.includes(key)}
                        onChange={() => toggleDay(key)}
                        style={{ width: "13px", height: "13px" }}
                      />
                      {label}
                    </label>
                  ))}
                </div>
              </div>

              {/* Open / close times */}
              <div style={{ display: "flex", gap: "16px", marginBottom: "20px" }}>
                <div style={{ flex: 1 }}>
                  <label htmlFor="open-time">Open time</label>
                  <input
                    id="open-time"
                    type="time"
                    value={openTime}
                    onChange={(e) => {
                      const val = e.target.value;
                      setOpenTime(val);
                      setSaveStatus(null);
                      checkDirty(isActive, weeklyOpenDays, val, closeTime, closedMessage);
                    }}
                    style={{
                      width: "100%", padding: "9px 12px",
                      border: "1px solid var(--border)", borderRadius: "var(--btn-radius)",
                      fontFamily: "inherit", fontSize: "15px",
                      color: "var(--text)", background: "var(--surface)",
                    }}
                  />
                </div>
                <div style={{ flex: 1 }}>
                  <label htmlFor="close-time">Close time</label>
                  <input
                    id="close-time"
                    type="time"
                    value={closeTime}
                    onChange={(e) => {
                      const val = e.target.value;
                      setCloseTime(val);
                      setSaveStatus(null);
                      checkDirty(isActive, weeklyOpenDays, openTime, val, closedMessage);
                    }}
                    style={{
                      width: "100%", padding: "9px 12px",
                      border: "1px solid var(--border)", borderRadius: "var(--btn-radius)",
                      fontFamily: "inherit", fontSize: "15px",
                      color: "var(--text)", background: "var(--surface)",
                    }}
                  />
                </div>
              </div>

              {/* Closed message */}
              <div style={{ marginBottom: "24px" }}>
                <label htmlFor="closed-message">Closed message (optional)</label>
                <textarea
                  id="closed-message"
                  value={closedMessage}
                  rows={3}
                  onChange={(e) => {
                    const val = e.target.value;
                    setClosedMessage(val);
                    setSaveStatus(null);
                    checkDirty(isActive, weeklyOpenDays, openTime, closeTime, val);
                  }}
                  placeholder="Message shown to patients when the form is closed…"
                  style={{
                    width: "100%", padding: "9px 12px",
                    border: "1px solid var(--border)", borderRadius: "var(--btn-radius)",
                    fontFamily: "inherit", fontSize: "15px",
                    color: "var(--text)", background: "var(--surface)",
                    resize: "vertical",
                  }}
                />
              </div>
            </>
          )}

          {/* Save button */}
          <div className="editor-actions">
            <button
              className="btn btn-primary"
              onClick={handleSave}
              disabled={isSaving}
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

          {/* ---- Override panel ---- */}
          {isActive && (
            <>
              <hr className="divider" />
              <p className="section-label">Temporary override</p>
              <p style={{ fontSize: "13px", color: "var(--text-muted)", marginBottom: "16px" }}>
                Force the form open or closed for a set period, overriding the normal schedule.
              </p>

              {hasActiveOverride && config && (
                <div className="alert alert-warning" style={{ marginBottom: "16px" }}>
                  Override active: form is forced{" "}
                  <strong>{config.override_status}</strong> until{" "}
                  {formatLondonTime(config.override_expires_at!)}
                  {config.override_message && (
                    <span style={{ display: "block", marginTop: "4px" }}>
                      Message: {config.override_message}
                    </span>
                  )}
                </div>
              )}

              {overrideError && (
                <div className="alert alert-error" style={{ marginBottom: "12px" }}>
                  {overrideError}
                </div>
              )}

              {!overrideFormOpen && (
                <div style={{ display: "flex", gap: "10px", flexWrap: "wrap" }}>
                  {hasActiveOverride ? (
                    <button
                      className="btn btn-outline"
                      onClick={handleClearOverride}
                      disabled={isOverrideSubmitting}
                    >
                      {isOverrideSubmitting ? "Clearing…" : "Clear override"}
                    </button>
                  ) : (
                    <>
                      <button
                        className="btn btn-outline"
                        onClick={() => openOverrideForm("open")}
                      >
                        Force open
                      </button>
                      <button
                        className="btn btn-outline"
                        onClick={() => openOverrideForm("closed")}
                      >
                        Force closed
                      </button>
                    </>
                  )}
                </div>
              )}

              {overrideFormOpen && (
                <div
                  style={{
                    border: "1px solid var(--border)",
                    borderRadius: "var(--card-radius)",
                    padding: "16px",
                    marginTop: "12px",
                    background: "var(--bg)",
                  }}
                >
                  <p style={{ fontSize: "14px", fontWeight: 500, marginBottom: "14px" }}>
                    Force {overrideFormStatus} until…
                  </p>

                  <div style={{ marginBottom: "12px" }}>
                    <label htmlFor="override-expiry">Expires at</label>
                    <input
                      id="override-expiry"
                      type="datetime-local"
                      value={overrideFormExpiry}
                      max={maxExpiryLocal()}
                      onChange={(e) => setOverrideFormExpiry(e.target.value)}
                      style={{
                        width: "100%", padding: "9px 12px",
                        border: "1px solid var(--border)", borderRadius: "var(--btn-radius)",
                        fontFamily: "inherit", fontSize: "15px",
                        color: "var(--text)", background: "var(--surface)",
                      }}
                    />
                  </div>

                  <div style={{ marginBottom: "12px" }}>
                    <label htmlFor="override-message">Message (optional)</label>
                    <input
                      id="override-message"
                      type="text"
                      value={overrideFormMessage}
                      onChange={(e) => setOverrideFormMessage(e.target.value)}
                      placeholder="Reason shown to patients…"
                    />
                  </div>

                  {overrideError && (
                    <div className="alert alert-error" style={{ marginTop: 0, marginBottom: "12px" }}>
                      {overrideError}
                    </div>
                  )}

                  <div style={{ display: "flex", gap: "10px" }}>
                    <button
                      className="btn btn-primary"
                      onClick={handleOverrideSubmit}
                      disabled={isOverrideSubmitting}
                      style={{ fontSize: "13px" }}
                    >
                      {isOverrideSubmitting ? "Saving…" : "Set override"}
                    </button>
                    <button
                      className="btn btn-outline"
                      onClick={() => setOverrideFormOpen(false)}
                      disabled={isOverrideSubmitting}
                      style={{ fontSize: "13px" }}
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              )}
            </>
          )}

          {/* ---- Exceptions panel ---- */}
          {isActive && (
            <>
              <hr className="divider" />
              <p className="section-label">Date exceptions</p>
              <p style={{ fontSize: "13px", color: "var(--text-muted)", marginBottom: "16px" }}>
                Set closures or different hours for specific dates (e.g. bank holidays, training days).
              </p>

              {exceptionsLoading && (
                <div className="loading-row" style={{ marginBottom: "12px" }}>
                  <span className="spinner dark" />
                  Loading exceptions...
                </div>
              )}

              {exceptionsError && (
                <div className="alert alert-error" style={{ marginBottom: "12px" }}>
                  Could not load exceptions: {exceptionsError}
                </div>
              )}

              {/* Exceptions list */}
              {!exceptionsLoading && exceptions.length > 0 && (
                <div style={{ marginBottom: "16px" }}>
                  {exceptions.map((exc) => (
                    <div
                      key={exc.exception_date}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "space-between",
                        padding: "10px 12px",
                        border: "1px solid var(--border)",
                        borderRadius: "var(--btn-radius)",
                        marginBottom: "6px",
                        background: "var(--surface)",
                        fontSize: "14px",
                      }}
                    >
                      <div>
                        <strong>{formatExceptionDate(exc.exception_date)}</strong>
                        <span style={{ marginLeft: "10px", color: "var(--text-muted)" }}>
                          {exc.exception_type === "closed"
                            ? "Closed"
                            : `${exc.open_time} – ${exc.close_time}`}
                        </span>
                        {exc.note && (
                          <span style={{ marginLeft: "10px", color: "var(--text-muted)", fontStyle: "italic" }}>
                            {exc.note}
                          </span>
                        )}
                      </div>
                      <button
                        className="btn btn-outline"
                        style={{ fontSize: "12px", padding: "2px 10px" }}
                        disabled={excDeleting === exc.exception_date}
                        onClick={() => handleDeleteException(exc.exception_date)}
                      >
                        {excDeleting === exc.exception_date ? "..." : "Delete"}
                      </button>
                    </div>
                  ))}
                </div>
              )}

              {!exceptionsLoading && exceptions.length === 0 && !exceptionsError && (
                <p style={{ fontSize: "13px", color: "var(--text-muted)", marginBottom: "12px" }}>
                  No upcoming exceptions.
                </p>
              )}

              {/* Add exception button / form */}
              {!exceptionFormOpen && (
                <button className="btn btn-outline" onClick={openExceptionForm}>
                  Add exception
                </button>
              )}

              {exceptionFormOpen && (
                <div
                  style={{
                    border: "1px solid var(--border)",
                    borderRadius: "var(--card-radius)",
                    padding: "16px",
                    marginTop: "12px",
                    background: "var(--bg)",
                  }}
                >
                  <div style={{ marginBottom: "12px" }}>
                    <label htmlFor="exc-date">Date</label>
                    <input
                      id="exc-date"
                      type="date"
                      value={excFormDate}
                      min={todayDateString()}
                      onChange={(e) => setExcFormDate(e.target.value)}
                      style={{
                        width: "100%", padding: "9px 12px",
                        border: "1px solid var(--border)", borderRadius: "var(--btn-radius)",
                        fontFamily: "inherit", fontSize: "15px",
                        color: "var(--text)", background: "var(--surface)",
                      }}
                    />
                  </div>

                  <div style={{ marginBottom: "12px" }}>
                    <label htmlFor="exc-type">Type</label>
                    <select
                      id="exc-type"
                      value={excFormType}
                      onChange={(e) => setExcFormType(e.target.value as "closed" | "custom_hours")}
                      style={{
                        width: "100%", padding: "9px 12px",
                        border: "1px solid var(--border)", borderRadius: "var(--btn-radius)",
                        fontFamily: "inherit", fontSize: "15px",
                        color: "var(--text)", background: "var(--surface)",
                      }}
                    >
                      <option value="closed">Closed all day</option>
                      <option value="custom_hours">Custom hours</option>
                    </select>
                  </div>

                  {excFormType === "custom_hours" && (
                    <div style={{ display: "flex", gap: "16px", marginBottom: "12px" }}>
                      <div style={{ flex: 1 }}>
                        <label htmlFor="exc-open-time">Open time</label>
                        <input
                          id="exc-open-time"
                          type="time"
                          value={excFormOpenTime}
                          onChange={(e) => setExcFormOpenTime(e.target.value)}
                          style={{
                            width: "100%", padding: "9px 12px",
                            border: "1px solid var(--border)", borderRadius: "var(--btn-radius)",
                            fontFamily: "inherit", fontSize: "15px",
                            color: "var(--text)", background: "var(--surface)",
                          }}
                        />
                      </div>
                      <div style={{ flex: 1 }}>
                        <label htmlFor="exc-close-time">Close time</label>
                        <input
                          id="exc-close-time"
                          type="time"
                          value={excFormCloseTime}
                          onChange={(e) => setExcFormCloseTime(e.target.value)}
                          style={{
                            width: "100%", padding: "9px 12px",
                            border: "1px solid var(--border)", borderRadius: "var(--btn-radius)",
                            fontFamily: "inherit", fontSize: "15px",
                            color: "var(--text)", background: "var(--surface)",
                          }}
                        />
                      </div>
                    </div>
                  )}

                  <div style={{ marginBottom: "12px" }}>
                    <label htmlFor="exc-note">Note (optional)</label>
                    <input
                      id="exc-note"
                      type="text"
                      value={excFormNote}
                      onChange={(e) => setExcFormNote(e.target.value)}
                      placeholder="e.g. Bank holiday, Staff training"
                    />
                  </div>

                  {excFormError && (
                    <div className="alert alert-error" style={{ marginTop: 0, marginBottom: "12px" }}>
                      {excFormError}
                    </div>
                  )}

                  <div style={{ display: "flex", gap: "10px" }}>
                    <button
                      className="btn btn-primary"
                      onClick={handleExceptionSubmit}
                      disabled={excFormSubmitting}
                      style={{ fontSize: "13px" }}
                    >
                      {excFormSubmitting ? "Saving..." : "Save exception"}
                    </button>
                    <button
                      className="btn btn-outline"
                      onClick={() => setExceptionFormOpen(false)}
                      disabled={excFormSubmitting}
                      style={{ fontSize: "13px" }}
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              )}
            </>
          )}
        </>
      )}
    </div>
  );
}

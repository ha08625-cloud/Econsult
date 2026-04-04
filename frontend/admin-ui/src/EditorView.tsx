/**
 * EditorView.tsx — main admin panel after authentication.
 *
 * Rendered by App once a valid session is confirmed.
 *
 * Layout: three-tab interface
 * - "Signposting"       — condition selector + SignpostingEditor
 * - "Availability"      — AvailabilityEditor
 * - "Practice settings" — email/contact configuration via PracticeSettingsTab
 *
 * Mounting strategy:
 * - AvailabilityEditor is always mounted, shown/hidden via display:none.
 *   This preserves its internal state across tab switches and allows
 *   availabilityUnsavedRef to be read synchronously at any time.
 * - Signposting content and Practice settings are conditionally rendered.
 *   SignpostingEditor (and its Quill instance) is destroyed when leaving
 *   the signposting tab and recreated on return. On recreation, Quill
 *   performs a fresh server fetch. This is intentional.
 * - PracticeSettingsTab is conditionally rendered and performs a fresh
 *   fetch on each mount. This is intentional.
 *
 * Unsaved change tracking:
 * - signpostingUnsavedRef: set by SignpostingEditor via onUnsavedChange
 * - availabilityUnsavedRef: set by AvailabilityEditor via onUnsavedChange
 * Both are refs (not state) so confirm dialogs can read them synchronously.
 *
 * Session expiry:
 * - If any child API call returns 401 (AuthError), the child calls
 *   onAuthError, which transitions App back to LoginView.
 * - Any unsaved data is lost on session expiry — no modal, no retry.
 *   This is intentional given the 24-hour session TTL. See arch_admin.md.
 */

import { useRef, useState } from "react";
import SignpostingEditor from "./SignpostingEditor";
import AvailabilityEditor from "./AvailabilityEditor";
import PracticeSettingsTab from "./PracticeSettingsTab";
import type { ConditionSummary } from "./types";

type Tab = "signposting" | "availability" | "practice_settings";

interface Props {
  conditions: ConditionSummary[];
  onAuthError: () => void;
}

export default function EditorView({ conditions, onAuthError }: Props) {
  const [activeTab, setActiveTab] = useState<Tab>("signposting");
  const [selectedId, setSelectedId] = useState<string | null>(
    conditions.length > 0 ? conditions[0].id : null
  );

  const signpostingUnsavedRef = useRef(false);
  const availabilityUnsavedRef = useRef(false);

  function handleTabChange(newTab: Tab) {
    if (newTab === activeTab) return;

    if (activeTab === "signposting" && signpostingUnsavedRef.current) {
      const ok = window.confirm(
        "You have unsaved changes. Switch tab and discard them?"
      );
      if (!ok) return;
      signpostingUnsavedRef.current = false;
    }

    if (activeTab === "availability" && availabilityUnsavedRef.current) {
      const ok = window.confirm(
        "You have unsaved changes. Switch tab and discard them?"
      );
      if (!ok) return;
      availabilityUnsavedRef.current = false;
    }

    setActiveTab(newTab);
  }

  function handleConditionChange(newId: string) {
    if (newId === selectedId) return;

    if (signpostingUnsavedRef.current) {
      const ok = window.confirm(
        "You have unsaved changes. Switch condition and discard them?"
      );
      if (!ok) return;
    }
    setSelectedId(newId);
    signpostingUnsavedRef.current = false;
  }

  return (
    <>
      {/* Tab bar */}
      <div className="tab-bar">
        <button
          className={`tab-btn${activeTab === "signposting" ? " active" : ""}`}
          onClick={() => handleTabChange("signposting")}
        >
          Signposting
        </button>
        <button
          className={`tab-btn${activeTab === "availability" ? " active" : ""}`}
          onClick={() => handleTabChange("availability")}
        >
          Availability
        </button>
        <button
          className={`tab-btn${activeTab === "practice_settings" ? " active" : ""}`}
          onClick={() => handleTabChange("practice_settings")}
        >
          Practice settings
        </button>
      </div>

      {/* Availability tab — always mounted, shown/hidden to preserve state */}
      <div style={{ display: activeTab === "availability" ? "block" : "none" }}>
        <AvailabilityEditor
          onUnsavedChange={(hasChanges) => {
            availabilityUnsavedRef.current = hasChanges;
          }}
          onAuthError={onAuthError}
        />
      </div>

      {/* Signposting tab — conditionally rendered */}
      {activeTab === "signposting" && (
        <>
          <div>
            <label htmlFor="condition-select">Condition</label>
            <select
              id="condition-select"
              value={selectedId ?? ""}
              onChange={(e) => handleConditionChange(e.target.value)}
            >
              {conditions.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.label}
                </option>
              ))}
            </select>
          </div>

          <hr className="divider" />

          <p className="section-label">Signposting content</p>

          {selectedId ? (
            <SignpostingEditor
              key={selectedId}
              conditionId={selectedId}
              onUnsavedChange={(hasChanges) => {
                signpostingUnsavedRef.current = hasChanges;
              }}
              onAuthError={onAuthError}
            />
          ) : (
            <div className="empty-state">Select a condition to begin.</div>
          )}
        </>
      )}

      {/* Practice settings tab — conditionally rendered, fetches on mount */}
      {activeTab === "practice_settings" && (
        <PracticeSettingsTab onAuthError={onAuthError} />
      )}
    </>
  );
}
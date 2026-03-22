/**
 * EditorView.tsx — main admin panel after authentication.
 *
 * Rendered by App once a valid token is held.
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
 *   fetch on each mount. This is intentional — practice details are not
 *   expected to change frequently.
 *
 * Unsaved change tracking:
 * - signpostingUnsavedRef: set by SignpostingEditor via onUnsavedChange
 * - availabilityUnsavedRef: set by AvailabilityEditor via onUnsavedChange
 * Both are refs (not state) so confirm dialogs can read them synchronously.
 * PracticeSettingsTab has no unsaved-change guard — single text field,
 * low stakes to lose on tab switch.
 *
 * Guard behaviour:
 * - Switching away from "signposting": confirms if signpostingUnsavedRef,
 *   resets ref on confirm.
 * - Switching away from "availability": confirms if availabilityUnsavedRef,
 *   resets ref on confirm. Explicit reset is required because AvailabilityEditor
 *   stays mounted and will not re-fetch (which would naturally reset the ref).
 * - Switching away from "practice_settings": no guard, no state.
 * - Condition change: always checks signpostingUnsavedRef, unchanged from
 *   previous behaviour.
 */

import { useRef, useState } from "react";
import SignpostingEditor from "./SignpostingEditor";
import AvailabilityEditor from "./AvailabilityEditor";
import PracticeSettingsTab from "./PracticeSettingsTab";
import type { ConditionSummary } from "./types";

type Tab = "signposting" | "availability" | "practice_settings";

interface Props {
  token: string;
  conditions: ConditionSummary[];
}

export default function EditorView({ token, conditions }: Props) {
  const [activeTab, setActiveTab] = useState<Tab>("signposting");
  const [selectedId, setSelectedId] = useState<string | null>(
    conditions.length > 0 ? conditions[0].id : null
  );

  // Track unsaved state via refs so confirm dialogs can read them
  // synchronously without needing to lift state out of child components.
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
      // Explicit reset: AvailabilityEditor stays mounted and will not
      // re-fetch, so the ref would remain stale without this reset.
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
          token={token}
          onUnsavedChange={(hasChanges) => {
            availabilityUnsavedRef.current = hasChanges;
          }}
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
            // key={selectedId} forces a full remount of SignpostingEditor on
            // every condition change. This destroys and recreates the Quill
            // instance cleanly rather than requiring complex re-initialisation
            // logic. Do not remove this key.
            <SignpostingEditor
              key={selectedId}
              conditionId={selectedId}
              token={token}
              onUnsavedChange={(hasChanges) => {
                signpostingUnsavedRef.current = hasChanges;
              }}
            />
          ) : (
            <div className="empty-state">Select a condition to begin.</div>
          )}
        </>
      )}

      {/* Practice settings tab — conditionally rendered, fetches on mount */}
      {activeTab === "practice_settings" && (
        <PracticeSettingsTab token={token} />
      )}
    </>
  );
}
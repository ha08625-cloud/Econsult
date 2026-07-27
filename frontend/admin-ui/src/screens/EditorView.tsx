/**
 * EditorView.tsx — main admin panel after authentication.
 *
 * Rendered by App once a valid session is confirmed.
 *
 * Layout: five-tab interface
 * - "Signposting"       — condition selector + SignpostingEditor
 * - "Availability"      — AvailabilityEditor
 * - "Practice settings" — email/contact configuration via PracticeSettingsTab
 * - "Audit log"         — read-only audit event viewer via AuditLogTab
 * - "Manage users"      — add/remove admin users via UsersTab
 *
 * Mounting strategy:
 * - AvailabilityEditor is always mounted, shown/hidden via display:none.
 *   This preserves its internal state across tab switches and allows
 *   availabilityUnsavedRef to be read synchronously at any time.
 * - All other tabs are conditionally rendered. Each performs a fresh fetch
 *   on mount. This is intentional.
 *
 * Unsaved change tracking:
 * - signpostingUnsavedRef: set by SignpostingEditor via onUnsavedChange
 * - availabilityUnsavedRef: set by AvailabilityEditor via onUnsavedChange
 * Both are refs (not state) so confirm dialogs can read them synchronously.
 * UsersTab has no unsaved state and requires no ref.
 *
 * Session expiry (sliding 60-minute TTL):
 * - If any child API call returns 401 (AuthError), the child calls
 *   onAuthError, which App handles by showing a login overlay above this
 *   component — EditorView itself stays mounted and unaware of the overlay.
 * - Unsaved data (tab, selected condition, editor contents) therefore
 *   survives session expiry. No refetch or remount happens on re-login;
 *   the user re-clicks whatever action failed. See arch_admin.md.
 */

import { useRef, useState } from "react";
import SignpostingEditor from "./SignpostingEditor";
import AvailabilityEditor from "./AvailabilityEditor";
import PracticeSettingsTab from "./PracticeSettingsTab";
import AuditLogTab from "./AuditLogTab";
import UsersTab from "./UsersTab";
import type { ConditionSummary } from "../types";

type Tab = "signposting" | "availability" | "practice_settings" | "audit_log" | "users";

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
        <button
          className={`tab-btn${activeTab === "audit_log" ? " active" : ""}`}
          onClick={() => handleTabChange("audit_log")}
        >
          Audit log
        </button>
        <button
          className={`tab-btn${activeTab === "users" ? " active" : ""}`}
          onClick={() => handleTabChange("users")}
        >
          Manage users
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

      {/* Audit log tab — conditionally rendered, fetches on mount */}
      {activeTab === "audit_log" && (
        <AuditLogTab onAuthError={onAuthError} />
      )}

      {/* Manage users tab — conditionally rendered, fetches on mount */}
      {activeTab === "users" && (
        <UsersTab onAuthError={onAuthError} />
      )}
    </>
  );
}
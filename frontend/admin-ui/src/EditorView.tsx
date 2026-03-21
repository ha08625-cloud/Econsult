/**
 * EditorView.tsx — main admin panel after authentication.
 *
 * Rendered by App once a valid token is held.
 * Contains:
 * - AvailabilityEditor card (opening hours configuration)
 * - Signposting editor card (per-condition patient information)
 *
 * Unsaved change tracking:
 * - signpostingUnsavedRef: set by SignpostingEditor via onUnsavedChange callback
 * - availabilityUnsavedRef: set by AvailabilityEditor via onUnsavedChange callback
 * Both are refs (not state) so the confirm dialog can read them synchronously
 * without triggering re-renders.
 */

import { useRef, useState } from "react";
import SignpostingEditor from "./SignpostingEditor";
import AvailabilityEditor from "./AvailabilityEditor";
import type { ConditionSummary } from "./types";

interface Props {
  token: string;
  conditions: ConditionSummary[];
}

export default function EditorView({ token, conditions }: Props) {
  const [selectedId, setSelectedId] = useState<string | null>(
    conditions.length > 0 ? conditions[0].id : null
  );

  // Track unsaved state via refs so the confirm dialog can read them
  // synchronously without needing to lift state out of child components.
  const signpostingUnsavedRef = useRef(false);
  const availabilityUnsavedRef = useRef(false);

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
      {/* Availability configuration card */}
      <AvailabilityEditor
        token={token}
        onUnsavedChange={(hasChanges) => {
          availabilityUnsavedRef.current = hasChanges;
        }}
      />

      <div style={{ height: "24px" }} />

      {/* Signposting editor card */}
      <div className="card">
        <p className="card-title">Signposting editor</p>
        <p className="card-subtitle">
          Add practice-specific information shown to patients before each
          condition form.
        </p>

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
      </div>
    </>
  );
}

/**
 * EditorView.tsx — main admin panel after authentication.
 *
 * Rendered by App once a valid token is held.
 * Contains:
 * - AvailabilityEditor card (opening hours configuration)
 * - Signposting editor card (per-condition patient information)
 *
 * Tracks unsaved signposting state via a ref so the confirm dialog
 * can read it without needing to lift state into App.
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

  // Track unsaved state via a ref so the confirm dialog can read it
  // without needing to lift state out of SignpostingEditor.
  const unsavedRef = useRef(false);

  function handleConditionChange(newId: string) {
    if (newId === selectedId) return;

    if (unsavedRef.current) {
      const ok = window.confirm(
        "You have unsaved changes. Switch condition and discard them?"
      );
      if (!ok) return;
    }
    setSelectedId(newId);
    unsavedRef.current = false;
  }

  return (
    <>
      {/* Availability configuration card */}
      <AvailabilityEditor token={token} />

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
              unsavedRef.current = hasChanges;
            }}
          />
        ) : (
          <div className="empty-state">Select a condition to begin.</div>
        )}
      </div>
    </>
  );
}

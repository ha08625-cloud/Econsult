/**
 * AuditLogTab.tsx — read-only audit log viewer.
 *
 * Displays a paginated table of admin audit events for this practice.
 * Filters: date range, actor email, action prefix.
 * Pagination: "Load more" button appends the next page to the existing list.
 *
 * Filter behaviour:
 * - Text filter inputs (actor, action) are debounced 400 ms to avoid a
 *   request per keystroke.
 * - Date inputs fetch immediately on change.
 * - Any filter change discards the current cursor and re-fetches from the top.
 *   This matches the cursor/filter independence contract in AuditRepository.
 *
 * Detail rendering:
 * Each row has a "Show detail" toggle. When expanded, DetailCell renders
 * a structured diff of the detail object:
 * - detail with before + after objects: show only changed keys, old and
 *   new value side by side.
 * - detail with before + after strings or arrays: show two labelled blocks.
 * - detail with only after (creation events): single labelled block.
 * - detail with only before (deletion events): single labelled block.
 * - flat detail objects (auth events): key-value pairs.
 * Values are rendered as plain text. HTML content is not rendered.
 *
 * Authentication: requests use the HttpOnly session cookie automatically.
 * If a request returns 401 (AuthError), onAuthError is called and App
 * transitions back to LoginView.
 *
 * This component is conditionally rendered by EditorView (destroyed and
 * recreated on each tab switch) so it always performs a fresh fetch on entry.
 */

import { useEffect, useRef, useState, useCallback } from "react";
import { fetchAuditLog, AuthError } from "../api";
import type { AuditEvent } from "../types";

interface Props {
  onAuthError: () => void;
}

// ---------------------------------------------------------------------------
// DetailCell
// ---------------------------------------------------------------------------

/**
 * Render a detail object as a structured diff.
 *
 * Accepts the raw detail value from an AuditEvent. Never renders HTML.
 * All values are stringified to plain text.
 */
function DetailCell({ detail }: { detail: Record<string, unknown> | null }) {
  if (detail === null) {
    return <span style={{ color: "var(--text-muted)", fontSize: "13px" }}>—</span>;
  }

  const hasBefore = "before" in detail;
  const hasAfter  = "after"  in detail;

  // before + after diff
  if (hasBefore && hasAfter) {
    const before = detail.before;
    const after  = detail.after;

    // Both are plain objects — show only changed keys
    if (
      before !== null && typeof before === "object" && !Array.isArray(before) &&
      after  !== null && typeof after  === "object" && !Array.isArray(after)
    ) {
      const beforeObj = before as Record<string, unknown>;
      const afterObj  = after  as Record<string, unknown>;
      const allKeys = Array.from(
        new Set([...Object.keys(beforeObj), ...Object.keys(afterObj)])
      );
      const changedKeys = allKeys.filter(
        (k) => JSON.stringify(beforeObj[k]) !== JSON.stringify(afterObj[k])
      );

      if (changedKeys.length === 0) {
        return (
          <span style={{ color: "var(--text-muted)", fontSize: "13px" }}>
            No changes detected
          </span>
        );
      }

      return (
        <table style={styles.diffTable}>
          <thead>
            <tr>
              <th style={styles.diffKeyCol}>Key</th>
              <th style={styles.diffValCol}>Before</th>
              <th style={styles.diffValCol}>After</th>
            </tr>
          </thead>
          <tbody>
            {changedKeys.map((k) => (
              <tr key={k}>
                <td style={styles.diffKey}>{k}</td>
                <td style={{ ...styles.diffVal, ...styles.diffBefore }}>
                  {renderValue(beforeObj[k])}
                </td>
                <td style={{ ...styles.diffVal, ...styles.diffAfter }}>
                  {renderValue(afterObj[k])}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      );
    }

    // Strings or arrays — show two labelled blocks
    return (
      <div>
        <LabelledBlock label="Before" value={before} />
        <LabelledBlock label="After"  value={after}  />
      </div>
    );
  }

  // Only after (creation events)
  if (hasAfter) {
    return <LabelledBlock label="After" value={detail.after} />;
  }

  // Only before (deletion events)
  if (hasBefore) {
    return <LabelledBlock label="Before" value={detail.before} />;
  }

  // Flat object — auth events and similar. Show key-value pairs.
  return (
    <table style={styles.diffTable}>
      <tbody>
        {Object.entries(detail).map(([k, v]) => (
          <tr key={k}>
            <td style={styles.diffKey}>{k}</td>
            <td style={styles.diffVal}>{renderValue(v)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function LabelledBlock({ label, value }: { label: string; value: unknown }) {
  return (
    <div style={{ marginBottom: "8px" }}>
      <span style={styles.blockLabel}>{label}</span>
      <pre style={styles.pre}>{renderValue(value)}</pre>
    </div>
  );
}

/** Stringify a value to plain text. Objects/arrays are JSON-formatted. */
function renderValue(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "string") return v;
  return JSON.stringify(v, null, 2);
}

// ---------------------------------------------------------------------------
// Styles (inline — consistent with rest of admin UI approach)
// ---------------------------------------------------------------------------

const styles = {
  diffTable: {
    borderCollapse: "collapse" as const,
    fontSize: "12px",
    fontFamily: "var(--font-mono, 'DM Mono', monospace)",
    width: "100%",
  },
  diffKeyCol: {
    width: "30%",
    padding: "4px 8px 4px 0",
    color: "var(--text-muted)",
    fontWeight: 600,
    textAlign: "left" as const,
    borderBottom: "1px solid var(--border)",
  },
  diffValCol: {
    width: "35%",
    padding: "4px 8px 4px 0",
    color: "var(--text-muted)",
    fontWeight: 600,
    textAlign: "left" as const,
    borderBottom: "1px solid var(--border)",
  },
  diffKey: {
    padding: "4px 8px 4px 0",
    color: "var(--text-muted)",
    fontWeight: 500,
    verticalAlign: "top" as const,
    whiteSpace: "nowrap" as const,
  },
  diffVal: {
    padding: "4px 8px 4px 0",
    verticalAlign: "top" as const,
    whiteSpace: "pre-wrap" as const,
    wordBreak: "break-word" as const,
    fontSize: "12px",
  },
  diffBefore: {
    color: "#c0392b",
    background: "#fdf2f2",
  },
  diffAfter: {
    color: "#1a7a4a",
    background: "#f0faf4",
  },
  blockLabel: {
    display: "block" as const,
    fontSize: "11px",
    fontWeight: 600,
    textTransform: "uppercase" as const,
    letterSpacing: "0.05em",
    color: "var(--text-muted)",
    marginBottom: "4px",
  },
  pre: {
    margin: 0,
    fontFamily: "var(--font-mono, 'DM Mono', monospace)",
    fontSize: "12px",
    whiteSpace: "pre-wrap" as const,
    wordBreak: "break-word" as const,
    color: "var(--text)",
    background: "var(--bg)",
    padding: "8px",
    borderRadius: "var(--btn-radius)",
    border: "1px solid var(--border)",
  },
};

// ---------------------------------------------------------------------------
// AuditLogTab
// ---------------------------------------------------------------------------

type LoadState = "loading" | "ready" | "error";

export default function AuditLogTab({ onAuthError }: Props) {
  const [events,     setEvents]     = useState<AuditEvent[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loadState,  setLoadState]  = useState<LoadState>("loading");
  const [loadError,  setLoadError]  = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);

  // Filter inputs — controlled
  const [fromDate, setFromDate] = useState("");
  const [toDate,   setToDate]   = useState("");
  const [actor,    setActor]    = useState("");
  const [action,   setAction]   = useState("");

  // Debounce timer ref for text inputs
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Which event IDs have their detail expanded
  const [expandedIds, setExpandedIds] = useState<Set<number>>(new Set());

  // ---------------------------------------------------------------------------
  // Fetch helpers
  // ---------------------------------------------------------------------------

  /**
   * Issue a fresh first-page fetch using current filter state.
   * Replaces the event list rather than appending.
   */
  const fetchFirstPage = useCallback(
    async (filters: {
      fromDate: string;
      toDate: string;
      actor: string;
      action: string;
    }) => {
      setLoadState("loading");
      setLoadError(null);
      setEvents([]);
      setNextCursor(null);
      setExpandedIds(new Set());

      try {
        const page = await fetchAuditLog({
          ...(filters.fromDate ? { from_date: filters.fromDate } : {}),
          ...(filters.toDate   ? { to_date:   filters.toDate   } : {}),
          ...(filters.actor    ? { actor:      filters.actor    } : {}),
          ...(filters.action   ? { action:     filters.action   } : {}),
        });
        setEvents(page.events);
        setNextCursor(page.next_cursor);
        setLoadState("ready");
      } catch (err) {
        if (err instanceof AuthError) { onAuthError(); return; }
        setLoadError(err instanceof Error ? err.message : "Failed to load audit log.");
        setLoadState("error");
      }
    },
    [onAuthError]
  );

  // Initial fetch on mount
  useEffect(() => {
    fetchFirstPage({ fromDate: "", toDate: "", actor: "", action: "" });
  }, [fetchFirstPage]);

  // ---------------------------------------------------------------------------
  // Filter change handlers
  // ---------------------------------------------------------------------------

  /** Trigger an immediate re-fetch with current input values. */
  function triggerRefetch(overrides: Partial<{
    fromDate: string; toDate: string; actor: string; action: string;
  }> = {}) {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    fetchFirstPage({
      fromDate: overrides.fromDate ?? fromDate,
      toDate:   overrides.toDate   ?? toDate,
      actor:    overrides.actor    ?? actor,
      action:   overrides.action   ?? action,
    });
  }

  /** Trigger a debounced re-fetch — used for text inputs. */
  function triggerDebouncedRefetch(overrides: Partial<{
    fromDate: string; toDate: string; actor: string; action: string;
  }> = {}) {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      fetchFirstPage({
        fromDate: overrides.fromDate ?? fromDate,
        toDate:   overrides.toDate   ?? toDate,
        actor:    overrides.actor    ?? actor,
        action:   overrides.action   ?? action,
      });
    }, 400);
  }

  function handleFromDateChange(value: string) {
    setFromDate(value);
    triggerRefetch({ fromDate: value });
  }

  function handleToDateChange(value: string) {
    setToDate(value);
    triggerRefetch({ toDate: value });
  }

  function handleActorChange(value: string) {
    setActor(value);
    triggerDebouncedRefetch({ actor: value });
  }

  function handleActionChange(value: string) {
    setAction(value);
    triggerDebouncedRefetch({ action: value });
  }

  // ---------------------------------------------------------------------------
  // Load more
  // ---------------------------------------------------------------------------

  async function handleLoadMore() {
    if (!nextCursor || loadingMore) return;
    setLoadingMore(true);

    try {
      const page = await fetchAuditLog({
        cursor: nextCursor,
        ...(fromDate ? { from_date: fromDate } : {}),
        ...(toDate   ? { to_date:   toDate   } : {}),
        ...(actor    ? { actor                } : {}),
        ...(action   ? { action               } : {}),
      });
      setEvents((prev) => [...prev, ...page.events]);
      setNextCursor(page.next_cursor);
    } catch (err) {
      if (err instanceof AuthError) { onAuthError(); return; }
      // Non-fatal — show inline error without replacing the list
      setLoadError(err instanceof Error ? err.message : "Failed to load more events.");
    } finally {
      setLoadingMore(false);
    }
  }

  // ---------------------------------------------------------------------------
  // Detail expansion
  // ---------------------------------------------------------------------------

  function toggleDetail(id: number) {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) { next.delete(id); } else { next.add(id); }
      return next;
    });
  }

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <div className="card">
      <p className="card-title">Audit log</p>
      <p className="card-subtitle">
        A record of all admin actions and authentication events for this practice.
      </p>

      {/* Filters */}
      <div style={filterRowStyle}>
        <div style={filterFieldStyle}>
          <label htmlFor="audit-from-date">From</label>
          <input
            id="audit-from-date"
            type="date"
            value={fromDate}
            onChange={(e) => handleFromDateChange(e.target.value)}
          />
        </div>
        <div style={filterFieldStyle}>
          <label htmlFor="audit-to-date">To</label>
          <input
            id="audit-to-date"
            type="date"
            value={toDate}
            onChange={(e) => handleToDateChange(e.target.value)}
          />
        </div>
        <div style={filterFieldStyle}>
          <label htmlFor="audit-actor">Actor</label>
          <input
            id="audit-actor"
            type="text"
            placeholder="email@example.com"
            value={actor}
            onChange={(e) => handleActorChange(e.target.value)}
          />
        </div>
        <div style={filterFieldStyle}>
          <label htmlFor="audit-action">Action</label>
          <input
            id="audit-action"
            type="text"
            placeholder="e.g. availability"
            value={action}
            onChange={(e) => handleActionChange(e.target.value)}
          />
        </div>
      </div>

      <hr className="divider" />

      {/* Loading state */}
      {loadState === "loading" && (
        <div className="loading-row">
          <span className="spinner dark" />
          Loading…
        </div>
      )}

      {/* Error state */}
      {loadState === "error" && loadError && (
        <div className="alert alert-error">{loadError}</div>
      )}

      {/* Results */}
      {loadState === "ready" && (
        <>
          {events.length === 0 ? (
            <div className="empty-state">No audit events found.</div>
          ) : (
            <div style={{ overflowX: "auto" }}>
              <table style={tableStyle}>
                <thead>
                  <tr>
                    <th style={thStyle}>Timestamp</th>
                    <th style={thStyle}>Actor</th>
                    <th style={thStyle}>Action</th>
                    <th style={thStyle}>Resource</th>
                    <th style={thStyle}>Detail</th>
                  </tr>
                </thead>
                <tbody>
                  {events.map((event) => {
                    const isExpanded = expandedIds.has(event.id);
                    return (
                      <>
                        <tr key={event.id} style={trStyle}>
                          <td style={tdStyle}>
                            <span className="mono" style={{ whiteSpace: "nowrap" }}>
                              {new Date(event.occurred_at).toLocaleString()}
                            </span>
                          </td>
                          <td style={tdStyle}>
                            <span style={{ fontSize: "13px" }}>{event.actor_email}</span>
                          </td>
                          <td style={tdStyle}>
                            <span className="mono" style={{ fontSize: "12px" }}>
                              {event.action}
                            </span>
                          </td>
                          <td style={tdStyle}>
                            <span style={{ fontSize: "13px", color: "var(--text-muted)" }}>
                              {event.resource ?? "—"}
                            </span>
                          </td>
                          <td style={tdStyle}>
                            {event.detail !== null ? (
                              <button
                                className="btn btn-ghost"
                                style={{ padding: "2px 8px", fontSize: "12px" }}
                                onClick={() => toggleDetail(event.id)}
                                aria-expanded={isExpanded}
                              >
                                {isExpanded ? "Hide" : "Show"}
                              </button>
                            ) : (
                              <span style={{ color: "var(--text-muted)", fontSize: "13px" }}>
                                —
                              </span>
                            )}
                          </td>
                        </tr>

                        {/* Expanded detail row */}
                        {isExpanded && (
                          <tr key={`${event.id}-detail`} style={detailRowStyle}>
                            <td colSpan={5} style={detailCellStyle}>
                              <DetailCell detail={event.detail} />
                            </td>
                          </tr>
                        )}
                      </>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {/* Load more */}
          {nextCursor && (
            <div style={{ marginTop: "16px", textAlign: "center" as const }}>
              <button
                className="btn btn-outline"
                onClick={handleLoadMore}
                disabled={loadingMore}
              >
                {loadingMore ? (
                  <>
                    <span className="spinner dark" style={{ width: "12px", height: "12px" }} />
                    Loading…
                  </>
                ) : (
                  "Load more"
                )}
              </button>
            </div>
          )}

          {/* Non-fatal load-more error */}
          {loadError && loadState === "ready" && (
            <div className="alert alert-error" style={{ marginTop: "12px" }}>
              {loadError}
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Layout styles
// ---------------------------------------------------------------------------

const filterRowStyle: React.CSSProperties = {
  display: "flex",
  flexWrap: "wrap",
  gap: "16px",
  marginBottom: "4px",
};

const filterFieldStyle: React.CSSProperties = {
  flex: "1 1 160px",
  minWidth: "140px",
};

const tableStyle: React.CSSProperties = {
  width: "100%",
  borderCollapse: "collapse",
  fontSize: "14px",
};

const thStyle: React.CSSProperties = {
  textAlign: "left",
  padding: "8px 12px 8px 0",
  borderBottom: "2px solid var(--border)",
  fontSize: "11px",
  fontWeight: 600,
  textTransform: "uppercase",
  letterSpacing: "0.05em",
  color: "var(--text-muted)",
  whiteSpace: "nowrap",
};

const trStyle: React.CSSProperties = {
  borderBottom: "1px solid var(--border)",
};

const tdStyle: React.CSSProperties = {
  padding: "10px 12px 10px 0",
  verticalAlign: "middle",
};

const detailRowStyle: React.CSSProperties = {
  borderBottom: "1px solid var(--border)",
  background: "var(--bg)",
};

const detailCellStyle: React.CSSProperties = {
  padding: "12px 12px 12px 0",
};
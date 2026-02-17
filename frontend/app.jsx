import React, { useState, useEffect } from "react";
import {
  initForm,
  updateForm,
  finishForm,
  getConditions,
  getConditionPresentation,
} from "./api";
import {
  ClientStateView,
  ClientAnswerReturn,
  SafetyMessage,
  ConditionSummary,
  ConditionPresentation,
} from "./types";

// ---------------------------------
// Helpers
// ---------------------------------

function initialiseEditableAnswers(
  clientState: ClientStateView
): Record<string, boolean | string | null> {
  return clientState.questions.reduce((acc, q) => {
    acc[q.answer_key] = q.current_value ?? null;
    return acc;
  }, {} as Record<string, boolean | string | null>);
}

// ---------------------------------
// App
// ---------------------------------

export default function App() {
  const [screen, setScreen] = useState
    "SELECT_CONDITION" | "FREE_TEXT" | "EDIT" | "REVIEW" | "DONE"
  >("SELECT_CONDITION");

  // Session state (populated after /form/init)
  const [runtimeId, setRuntimeId] = useState<string | null>(null);
  const [version, setVersion] = useState<number | null>(null);
  const [clientState, setClientState] = useState<ClientStateView | null>(null);
  const [editableAnswers, setEditableAnswers] = useState<Record
    string,
    boolean | string | null
  > | null>(null);
  const [safetyMessages, setSafetyMessages] = useState<SafetyMessage[]>([]);

  // Shared UI state
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [fatalError, setFatalError] = useState<string | null>(null);

  // Screen 0 state (condition discovery)
  const [conditions, setConditions] = useState<ConditionSummary[] | null>(null);
  const [selectedConditionId, setSelectedConditionId] = useState<string | null>(null);

  // Screen 1 state (presentation framing)
  const [presentation, setPresentation] = useState<ConditionPresentation | null>(null);
  const [freeText, setFreeText] = useState<string>("");

  // ---------------------------------
  // Condition list fetch (Screen 0)
  // ---------------------------------

  useEffect(() => {
    if (screen !== "SELECT_CONDITION") return;
    if (conditions !== null) return;

    let cancelled = false;

    async function fetchConditions() {
      try {
        const res = await getConditions();
        if (cancelled) return;
        if (!res.conditions || res.conditions.length === 0) {
          setFatalError("No conditions available");
          return;
        }
        setConditions(res.conditions);
      } catch (e) {
        if (!cancelled) {
          setFatalError(String(e));
        }
      }
    }

    fetchConditions();

    return () => {
      cancelled = true;
    };
  }, [screen, conditions]);

  // ---------------------------------
  // Fatal error handling
  // ---------------------------------

  if (fatalError) {
    return (
      <div>
        <h1>Fatal error</h1>
        <p>{fatalError}</p>
        <button
          onClick={() => {
            setFatalError(null);
            setScreen("SELECT_CONDITION");
            // Session state
            setRuntimeId(null);
            setVersion(null);
            setClientState(null);
            setEditableAnswers(null);
            setSafetyMessages([]);
            // Screen 0-1 state
            setConditions(null);
            setSelectedConditionId(null);
            setPresentation(null);
            setFreeText("");
          }}
        >
          Restart
        </button>
      </div>
    );
  }

  // ---------------------------------
  // Screen 0: SELECT_CONDITION
  // ---------------------------------

  if (screen === "SELECT_CONDITION") {
    return (
      <div>
        <h1>Start consultation</h1>

        {conditions === null ? (
          <p>Loading conditions...</p>
        ) : (
          <>
            <label>
              What is your consultation about?
              <select
                value={selectedConditionId ?? ""}
                onChange={(e) => setSelectedConditionId(e.target.value || null)}
              >
                <option value="">-- Select --</option>
                {conditions.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.label}
                  </option>
                ))}
              </select>
            </label>

            <button
              disabled={selectedConditionId === null}
              onClick={() => setScreen("FREE_TEXT")}
            >
              Continue
            </button>
          </>
        )}
      </div>
    );
  }

  // ---------------------------------
  // Screen 1: FREE_TEXT
  // ---------------------------------

  if (screen === "FREE_TEXT") {
    if (selectedConditionId === null) {
      setFatalError("No condition selected");
      return null;
    }

    // Fetch presentation on entry if not already loaded
    if (presentation === null && !isSubmitting) {
      (async () => {
        try {
          const res = await getConditionPresentation(selectedConditionId);
          setPresentation(res);
        } catch (e) {
          setFatalError(String(e));
        }
      })();

      return (
        <div>
          <p>Loading...</p>
        </div>
      );
    }

    if (presentation === null) {
      return (
        <div>
          <p>Loading...</p>
        </div>
      );
    }

    return (
      <div>
        <h1>{presentation.label}</h1>

        {/* Universal safety warning - always shown */}
        <div style={{
          backgroundColor: "#fee",
          padding: "1em",
          marginBottom: "1em",
          border: "1px solid #c00",
          borderRadius: "4px",
        }}>
          <strong>Important safety information</strong>
          <p style={{ marginBottom: 0 }}>{presentation.universal_safety_warning}</p>
        </div>

        {/* Practice-specific signposting - only shown if configured */}
        {presentation.practice_signposting &&
          presentation.practice_signposting.length > 0 && (
            <div style={{
              backgroundColor: "#eef",
              padding: "1em",
              marginBottom: "1em",
              border: "1px solid #00c",
              borderRadius: "4px",
            }}>
              <strong>Information from your practice</strong>
              {presentation.practice_signposting.map((info, i) => (
                <p key={i} style={{ marginBottom: i === presentation.practice_signposting!.length - 1 ? 0 : undefined }}>
                  {info}
                </p>
              ))}
            </div>
          )}

        <label>
          {presentation.free_text_prompt ?? "Describe your symptoms"}
          <textarea
            value={freeText}
            onChange={(e) => setFreeText(e.target.value)}
          />
        </label>

        <button
          disabled={isSubmitting}
          onClick={async () => {
            try {
              setIsSubmitting(true);
              const res = await initForm(selectedConditionId, freeText || null);
              // Store session state
              setRuntimeId(res.runtime_id);
              setVersion(res.version);
              setClientState(res.client_state);
              setEditableAnswers(initialiseEditableAnswers(res.client_state));
              // Discard Screen 0-1 transient state
              setPresentation(null);
              setSelectedConditionId(null);
              setFreeText("");
              // Advance
              setScreen("EDIT");
            } catch (e) {
              setFatalError(String(e));
            } finally {
              setIsSubmitting(false);
            }
          }}
        >
          {isSubmitting ? "Submitting\u2026" : "Continue"}
        </button>
      </div>
    );
  }

  // ---------------------------------
  // Screen 2: EDIT
  // ---------------------------------

  if (screen === "EDIT") {
    if (!clientState || !editableAnswers || runtimeId === null || version === null) {
      setFatalError("Invalid EDIT state");
      return null;
    }

    const allRequiredAnswered = clientState.questions.every((q) => {
      if (!q.required) return true;
      const v = editableAnswers[q.answer_key];
      return v !== null && v !== undefined && v !== "";
    });

    return (
      <div>
        <h1>{clientState.condition_label}</h1>

        {clientState.free_text && (
          <div>
            <h3>Your description</h3>
            <p>{clientState.free_text}</p>
          </div>
        )}

        <form
          onSubmit={(e) => {
            e.preventDefault();
          }}
        >
          {clientState.questions.map((q) => (
            <div key={q.answer_key}>
              <label>
                {q.question_text}
                {q.required && " *"}
              </label>

              {q.answer_type === "boolean" ? (
                <div>
                  <label>
                    <input
                      type="radio"
                      name={q.answer_key}
                      checked={editableAnswers[q.answer_key] === true}
                      onChange={() => {
                        setEditableAnswers({
                          ...editableAnswers,
                          [q.answer_key]: true,
                        });
                      }}
                    />
                    Yes
                  </label>
                  <label>
                    <input
                      type="radio"
                      name={q.answer_key}
                      checked={editableAnswers[q.answer_key] === false}
                      onChange={() => {
                        setEditableAnswers({
                          ...editableAnswers,
                          [q.answer_key]: false,
                        });
                      }}
                    />
                    No
                  </label>
                </div>
              ) : (
                <input
                  type="text"
                  value={(editableAnswers[q.answer_key] as string | null) || ""}
                  onChange={(e) => {
                    setEditableAnswers({
                      ...editableAnswers,
                      [q.answer_key]: e.target.value,
                    });
                  }}
                />
              )}

              {q.suggested && (
                <div>
                  <small>Suggested answer — please check</small>
                </div>
              )}
            </div>
          ))}

          <button
            disabled={!allRequiredAnswered || isSubmitting}
            onClick={async () => {
              try {
                setIsSubmitting(true);
                const payload: ClientAnswerReturn = {
                  runtime_id: runtimeId,
                  base_version: version,
                  answers: editableAnswers,
                };
                const res = await updateForm(payload);
                setVersion(res.version);
                setClientState(res.client_state);
                setSafetyMessages(res.safety_messages);
                setEditableAnswers(null); // discard
                setScreen("REVIEW");
              } catch (e) {
                setFatalError(String(e));
              } finally {
                setIsSubmitting(false);
              }
            }}
          >
            {isSubmitting ? "Submitting\u2026" : "Review"}
          </button>
        </form>
      </div>
    );
  }

  // ---------------------------------
  // Screen 3: REVIEW
  // ---------------------------------

  if (screen === "REVIEW") {
    if (!clientState || runtimeId === null || version === null) {
      setFatalError("Invalid REVIEW state");
      return null;
    }

    const hasSafetyBlock = safetyMessages.length > 0;

    return (
      <div>
        <h1>Review</h1>

        <h3>{clientState.condition_label}</h3>

        {clientState.free_text && <p>{clientState.free_text}</p>}

        <ul>
          {clientState.questions.map((q) => (
            <li key={q.answer_key}>
              <strong>{q.question_text}</strong>:{" "}
              {q.current_value === null || q.current_value === ""
                ? "(not answered)"
                : String(q.current_value)}
            </li>
          ))}
        </ul>

        {hasSafetyBlock && (
          <div>
            <h3>Important</h3>
            {safetyMessages.map((m) => (
              <p key={m.rule_id}>{m.message}</p>
            ))}
          </div>
        )}

        <button
          onClick={() => {
            setEditableAnswers(initialiseEditableAnswers(clientState));
            setScreen("EDIT");
          }}
        >
          Back
        </button>

        <button
          disabled={hasSafetyBlock || isSubmitting}
          onClick={async () => {
            try {
              setIsSubmitting(true);
              await finishForm(runtimeId, version);
              setScreen("DONE");
            } catch (e) {
              setFatalError(String(e));
            } finally {
              setIsSubmitting(false);
            }
          }}
        >
          {isSubmitting ? "Submitting\u2026" : "Submit"}
        </button>
      </div>
    );
  }

  // ---------------------------------
  // Screen 4: DONE
  // ---------------------------------

  if (screen === "DONE") {
    return (
      <div>
        <h1>Thank you</h1>
        <p>Your consultation has been submitted.</p>
      </div>
    );
  }

  return null;
}

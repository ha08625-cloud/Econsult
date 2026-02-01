import React, { useState } from "react";
import { initForm, updateForm, finishForm } from "./api";
import {
  ClientStateView,
  ClientAnswerReturn,
  SafetyMessage,
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
  const [screen, setScreen] = useState<"INIT" | "EDIT" | "REVIEW" | "DONE">("INIT");

  const [runtimeId, setRuntimeId] = useState<string | null>(null);
  const [version, setVersion] = useState<number | null>(null);

  const [clientState, setClientState] = useState<ClientStateView | null>(null);
  const [editableAnswers, setEditableAnswers] = useState<Record<
    string,
    boolean | string | null
  > | null>(null);

  const [safetyMessages, setSafetyMessages] = useState<SafetyMessage[]>([]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [fatalError, setFatalError] = useState<string | null>(null);

  // INIT screen local state
  const [condition, setCondition] = useState("uti1");
  const [freeText, setFreeText] = useState<string>("");

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
            setScreen("INIT");
            setRuntimeId(null);
            setVersion(null);
            setClientState(null);
            setEditableAnswers(null);
            setSafetyMessages([]);
          }}
        >
          Restart
        </button>
      </div>
    );
  }

  // ---------------------------------
  // Screen: INIT
  // ---------------------------------

  if (screen === "INIT") {
    return (
      <div>
        <h1>Start consultation</h1>

        <label>
          Condition
          <select value={condition} onChange={(e) => setCondition(e.target.value)}>
            <option value="uti1">Urinary symptoms</option>
          </select>
        </label>

        <label>
          Describe your symptoms
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
              const res = await initForm(condition, freeText || null);
              setRuntimeId(res.runtime_id);
              setVersion(res.version);
              setClientState(res.client_state);
              setEditableAnswers(initialiseEditableAnswers(res.client_state));
              setScreen("EDIT");
            } catch (e) {
              setFatalError(String(e));
            } finally {
              setIsSubmitting(false);
            }
          }}
        >
          {isSubmitting ? "Submitting…" : "Continue"}
        </button>
      </div>
    );
  }

  // ---------------------------------
  // Screen: EDIT
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
            {isSubmitting ? "Submitting…" : "Review"}
          </button>
        </form>
      </div>
    );
  }

  // ---------------------------------
  // Screen: REVIEW
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
              {q.question_text}: {String(q.current_value)}
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
              const payload: ClientAnswerReturn = {
                runtime_id: runtimeId,
                base_version: version,
                answers: initialiseEditableAnswers(clientState),
              };
              await finishForm(payload);
              setScreen("DONE");
            } catch (e) {
              setFatalError(String(e));
            } finally {
              setIsSubmitting(false);
            }
          }}
        >
          {isSubmitting ? "Submitting…" : "Submit"}
        </button>
      </div>
    );
  }

  // ---------------------------------
  // Screen: DONE
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

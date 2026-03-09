import React, { useState, useEffect } from "react";
import {
  getSafetyWarning,
  initForm,
  updateForm,
  finishForm,
  getConditions,
  getConditionPresentation,
  friendlyErrorMessage,
} from "./api";
import type {
  ClientStateView,
  ClientAnswerReturn,
  SafetyMessage,
  ConditionSummary,
  ConditionPresentation,
} from "./types";
import ConditionCombobox from "./ConditionCombobox";
import { GENERAL_CONSULTATION_ID } from "./constants";

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

function PageShell({ children }: { children: React.ReactNode }) {
  return (
    <>
      <header className="page-header">
        <span className="page-header-title">Online Consultation</span>
      </header>
      <div className="page-container">
        <div className="screen-card">{children}</div>
      </div>
    </>
  );
}

function InlineError({ message }: { message: string }) {
  return (
    <div className="alert alert-danger" style={{ marginTop: "16px", marginBottom: 0 }}>
      <p style={{ margin: 0 }}>{message}</p>
    </div>
  );
}

// ---------------------------------
// App
// ---------------------------------

export default function App() {
  const [screen, setScreen] = useState<
    "SAFETY_WARNING" | "SELECT_CONDITION" | "FREE_TEXT" | "EDIT" | "REVIEW" | "DONE"
  >("SAFETY_WARNING");

  // Session state (populated after /form/init)
  const [runtimeId, setRuntimeId] = useState<string | null>(null);
  const [version, setVersion] = useState<number | null>(null);
  const [clientState, setClientState] = useState<ClientStateView | null>(null);
  const [editableAnswers, setEditableAnswers] = useState<Record<string, boolean | string | null> | null>(null);
  const [additionalText, setAdditionalText] = useState<string>("");
  const [safetyMessages, setSafetyMessages] = useState<SafetyMessage[]>([]);

  // Shared UI state
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [fatalError, setFatalError] = useState<string | null>(null);
  const [screenError, setScreenError] = useState<string | null>(null);

  // Screen 0 state (safety gate)
  const [safetyWarningText, setSafetyWarningText] = useState<string | null>(null);
  const [safetyConfirmed, setSafetyConfirmed] = useState(false);

  // Screen 1 state (condition discovery)
  const [conditions, setConditions] = useState<ConditionSummary[] | null>(null);
  const [selectedConditionId, setSelectedConditionId] = useState<string | null>(null);

  // Screen 2 state (presentation framing)
  const [presentation, setPresentation] = useState<ConditionPresentation | null>(null);
  const [freeText, setFreeText] = useState<string>("");

  // Clear inline error on screen change
  useEffect(() => {
    setScreenError(null);
  }, [screen]);

  // ---------------------------------
  // Safety warning fetch (Screen 0)
  // ---------------------------------

  useEffect(() => {
    if (screen !== "SAFETY_WARNING") return;
    if (safetyWarningText !== null) return;

    let cancelled = false;

    async function fetchWarning() {
      try {
        const res = await getSafetyWarning();
        if (!cancelled) setSafetyWarningText(res.universal_safety_warning);
      } catch (e) {
        if (!cancelled) setScreenError(friendlyErrorMessage(e));
      }
    }

    fetchWarning();

    return () => { cancelled = true; };
  }, [screen, safetyWarningText]);

  // ---------------------------------
  // Condition list fetch (Screen 1)
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
          setFatalError("No conditions are currently available. Please contact the practice directly.");
          return;
        }
        setConditions(res.conditions);
      } catch (e) {
        if (!cancelled) {
          setFatalError(friendlyErrorMessage(e));
        }
      }
    }

    fetchConditions();

    return () => { cancelled = true; };
  }, [screen, conditions]);

  // ---------------------------------
  // Fatal error handling
  // ---------------------------------

  if (fatalError) {
    return (
      <PageShell>
        <h1>Unable to load the form</h1>
        <div className="alert alert-danger">
          <p>{fatalError}</p>
        </div>
        <p style={{ color: "var(--text-muted)", fontSize: "14px", marginTop: "12px" }}>
          If this problem persists, please contact the practice directly.
        </p>
        <div className="btn-row">
          <button
            className="btn btn-primary"
            onClick={() => {
              setFatalError(null);
              setScreen("SAFETY_WARNING");
              setSafetyWarningText(null);
              setSafetyConfirmed(false);
              setRuntimeId(null);
              setVersion(null);
              setClientState(null);
              setEditableAnswers(null);
              setAdditionalText("");
              setSafetyMessages([]);
              setConditions(null);
              setSelectedConditionId(null);
              setPresentation(null);
              setFreeText("");
            }}
          >
            Try again
          </button>
        </div>
      </PageShell>
    );
  }

  // ---------------------------------
  // Screen 0: SAFETY_WARNING
  // ---------------------------------

  if (screen === "SAFETY_WARNING") {
    return (
      <PageShell>
        <h1>Before you continue</h1>

        {safetyWarningText === null && !screenError && (
          <p className="status-text">Loading...</p>
        )}

        {screenError && (
          <>
            <InlineError message={screenError} />
            <div className="btn-row">
              <button
                className="btn btn-primary"
                onClick={() => {
                  setScreenError(null);
                  setSafetyWarningText(null);
                }}
              >
                Try again
              </button>
            </div>
          </>
        )}

        {safetyWarningText !== null && (
          <>
            <div className="alert alert-danger">
              <strong>Important — read before continuing</strong>
              <p>{safetyWarningText}</p>
            </div>

            <div className="safety-confirm-row">
              <label className="safety-confirm-label">
                <input
                  type="checkbox"
                  checked={safetyConfirmed}
                  onChange={(e) => setSafetyConfirmed(e.target.checked)}
                />
                <span>I confirm that none of the above apply to me</span>
              </label>
            </div>

            {!safetyConfirmed && (
              <p className="safety-gate-hint">
                If any of the above apply to you, please call 999 or go to A&amp;E immediately. Do not use this form.
              </p>
            )}

            <div className="btn-row">
              <button
                className="btn btn-primary"
                disabled={!safetyConfirmed}
                onClick={() => setScreen("SELECT_CONDITION")}
              >
                Continue
              </button>
            </div>
          </>
        )}
      </PageShell>
    );
  }

  // ---------------------------------
  // Screen 1: SELECT_CONDITION
  // ---------------------------------

  if (screen === "SELECT_CONDITION") {
    const selectableConditions: ConditionSummary[] = conditions
      ? conditions.filter((c) => c.id !== GENERAL_CONSULTATION_ID)
      : [];

    function handleBlankForm() {
      setSelectedConditionId(GENERAL_CONSULTATION_ID);
      setScreen("FREE_TEXT");
    }

    return (
      <PageShell>
        <h1>Start your consultation</h1>

        {conditions === null ? (
          <p className="status-text">Loading...</p>
        ) : (
          <>
            <div className="field">
              <label htmlFor="condition-combobox-input">
                What is your consultation about?
              </label>
              <ConditionCombobox
                conditions={selectableConditions}
                selectedId={selectedConditionId}
                onChange={setSelectedConditionId}
              />
            </div>

            <div className="btn-row">
              <button
                className="btn btn-primary"
                disabled={selectedConditionId === null}
                onClick={() => setScreen("FREE_TEXT")}
              >
                Continue
              </button>
            </div>

            <hr className="divider" />

            <p style={{ color: "var(--text-muted)", fontSize: "14px", marginBottom: "12px" }}>
              If you cannot find a condition that matches your problem, you can
              use a blank form instead.
            </p>
            <button className="btn btn-secondary" onClick={handleBlankForm}>
              Use blank form
            </button>
          </>
        )}
      </PageShell>
    );
  }

  // ---------------------------------
  // Screen 2: FREE_TEXT
  // ---------------------------------

  if (screen === "FREE_TEXT") {
    if (selectedConditionId === null) {
      setFatalError("No condition selected");
      return null;
    }

    if (presentation === null && !isSubmitting) {
      (async () => {
        try {
          const res = await getConditionPresentation(selectedConditionId);
          setPresentation(res);
        } catch (e) {
          setScreenError(friendlyErrorMessage(e));
          setPresentation(null);
        }
      })();

      return (
        <PageShell>
          {screenError ? (
            <>
              <h1>Something went wrong</h1>
              <InlineError message={screenError} />
              <div className="btn-row">
                <button
                  className="btn btn-secondary"
                  onClick={() => {
                    setScreenError(null);
                    setScreen("SELECT_CONDITION");
                  }}
                >
                  Back
                </button>
                <button
                  className="btn btn-primary"
                  onClick={() => {
                    setScreenError(null);
                    setPresentation(null);
                  }}
                >
                  Try again
                </button>
              </div>
            </>
          ) : (
            <p className="status-text">Loading...</p>
          )}
        </PageShell>
      );
    }

    if (presentation === null) {
      return (
        <PageShell>
          <p className="status-text">Loading...</p>
        </PageShell>
      );
    }

    return (
      <PageShell>
        <h1>{presentation.label}</h1>

        {presentation.practice_signposting &&
          presentation.practice_signposting.length > 0 && (
            <div className="alert alert-info">
              <strong>Information from your practice</strong>
              {presentation.practice_signposting.map((info, i) => (
                <p key={i}>{info}</p>
              ))}
            </div>
          )}

        <div className="field">
          <label htmlFor="free-text-input">
            {presentation.free_text_prompt ?? "Describe your symptoms"}
          </label>
          <textarea
            id="free-text-input"
            value={freeText}
            onChange={(e) => {
              setFreeText(e.target.value);
              if (screenError) setScreenError(null);
            }}
            rows={5}
          />
        </div>

        {screenError && <InlineError message={screenError} />}

        <div className="btn-row">
          <button
            className="btn btn-primary"
            disabled={isSubmitting}
            onClick={async () => {
              setScreenError(null);
              try {
                setIsSubmitting(true);
                const res = await initForm(selectedConditionId, freeText || null);
                setRuntimeId(res.runtime_id);
                setVersion(res.version);
                setClientState(res.client_state);
                setEditableAnswers(initialiseEditableAnswers(res.client_state));
                setAdditionalText(res.client_state.additional_text ?? "");
                setPresentation(null);
                setSelectedConditionId(null);
                setFreeText("");
                setScreen("EDIT");
              } catch (e) {
                setScreenError(friendlyErrorMessage(e));
              } finally {
                setIsSubmitting(false);
              }
            }}
          >
            {isSubmitting ? "Please wait\u2026" : "Continue"}
          </button>
        </div>
      </PageShell>
    );
  }

  // ---------------------------------
  // Screen 3: EDIT
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
      <PageShell>
        <h1>{clientState.condition_label}</h1>

        {clientState.free_text && (
          <div className="description-box">
            {clientState.free_text}
          </div>
        )}

        <form onSubmit={(e) => e.preventDefault()}>
          {clientState.questions.map((q) => (
            <div
              key={q.answer_key}
              className={`question-card${q.suggested ? " suggested" : ""}`}
            >
              <label>
                {q.question_text}
                {q.required && <span style={{ color: "var(--danger)", marginLeft: "4px" }}>*</span>}
              </label>

              {q.answer_type === "boolean" ? (
                <div className="radio-group">
                  <label
                    className={`radio-option${editableAnswers[q.answer_key] === true ? " selected" : ""}`}
                  >
                    <input
                      type="radio"
                      name={q.answer_key}
                      checked={editableAnswers[q.answer_key] === true}
                      onChange={() => {
                        setEditableAnswers({ ...editableAnswers, [q.answer_key]: true });
                        if (screenError) setScreenError(null);
                      }}
                    />
                    Yes
                  </label>
                  <label
                    className={`radio-option${editableAnswers[q.answer_key] === false ? " selected" : ""}`}
                  >
                    <input
                      type="radio"
                      name={q.answer_key}
                      checked={editableAnswers[q.answer_key] === false}
                      onChange={() => {
                        setEditableAnswers({ ...editableAnswers, [q.answer_key]: false });
                        if (screenError) setScreenError(null);
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
                    setEditableAnswers({ ...editableAnswers, [q.answer_key]: e.target.value });
                    if (screenError) setScreenError(null);
                  }}
                />
              )}

              {q.suggested && (
                <span className="suggested-badge">
                  Pre-filled from your description — please check
                </span>
              )}
            </div>
          ))}

          <div className="field mt-md">
            <label htmlFor="additional-text">
              Additional information (optional)
            </label>
            <p style={{ fontSize: "14px", color: "var(--text-muted)", marginBottom: "8px", fontWeight: 400 }}>
              If you answered yes to any symptoms above, you can give details here.
            </p>
            <textarea
              id="additional-text"
              value={additionalText}
              onChange={(e) => {
                setAdditionalText(e.target.value);
                if (screenError) setScreenError(null);
              }}
              rows={4}
            />
          </div>

          {screenError && <InlineError message={screenError} />}

          <div className="btn-row">
            <button
              className="btn btn-primary"
              disabled={!allRequiredAnswered || isSubmitting}
              onClick={async () => {
                setScreenError(null);
                try {
                  setIsSubmitting(true);
                  const payload: ClientAnswerReturn = {
                    runtime_id: runtimeId,
                    base_version: version,
                    answers: editableAnswers,
                    additional_text: additionalText.trim() || null,
                  };
                  const res = await updateForm(payload);
                  setVersion(res.version);
                  setClientState(res.client_state);
                  setSafetyMessages(res.safety_messages);
                  setEditableAnswers(null);
                  setScreen("REVIEW");
                } catch (e) {
                  setScreenError(friendlyErrorMessage(e));
                } finally {
                  setIsSubmitting(false);
                }
              }}
            >
              {isSubmitting ? "Please wait\u2026" : "Review answers"}
            </button>
          </div>
        </form>
      </PageShell>
    );
  }

  // ---------------------------------
  // Screen 4: REVIEW
  // ---------------------------------

  if (screen === "REVIEW") {
    if (!clientState || runtimeId === null || version === null) {
      setFatalError("Invalid REVIEW state");
      return null;
    }

    const hasSafetyBlock = safetyMessages.length > 0;

    return (
      <PageShell>
        <h1>Review your answers</h1>

        <h3>{clientState.condition_label}</h3>

        {clientState.free_text && (
          <div className="description-box mb-md">
            {clientState.free_text}
          </div>
        )}

        <ul className="review-list">
          {clientState.questions.map((q) => (
            <li key={q.answer_key} className="review-item">
              <span className="review-question">{q.question_text}</span>
              <span className="review-answer">
                {q.current_value === null || q.current_value === ""
                  ? <em style={{ color: "var(--text-muted)", fontWeight: 400 }}>Not answered</em>
                  : String(q.current_value) === "true"
                    ? "Yes"
                    : String(q.current_value) === "false"
                      ? "No"
                      : String(q.current_value)}
              </span>
            </li>
          ))}
        </ul>

        {clientState.additional_text && (
          <>
            <h3>Additional information</h3>
            <div className="description-box mb-md">
              {clientState.additional_text}
            </div>
          </>
        )}

        {hasSafetyBlock && (
          <div className="alert alert-danger">
            <strong>Important — action required</strong>
            {safetyMessages.map((m) => (
              <p key={m.rule_id}>{m.message}</p>
            ))}
          </div>
        )}

        {screenError && <InlineError message={screenError} />}

        <div className="btn-row">
          <button
            className="btn btn-secondary"
            onClick={() => {
              setEditableAnswers(initialiseEditableAnswers(clientState));
              setScreen("EDIT");
            }}
          >
            Back
          </button>

          <button
            className="btn btn-primary"
            disabled={hasSafetyBlock || isSubmitting}
            onClick={async () => {
              setScreenError(null);
              try {
                setIsSubmitting(true);
                await finishForm(runtimeId, version);
                setScreen("DONE");
              } catch (e) {
                setScreenError(friendlyErrorMessage(e));
              } finally {
                setIsSubmitting(false);
              }
            }}
          >
            {isSubmitting ? "Submitting\u2026" : "Submit"}
          </button>
        </div>
      </PageShell>
    );
  }

  // ---------------------------------
  // Screen 5: DONE
  // ---------------------------------

  if (screen === "DONE") {
    return (
      <PageShell>
        <div className="done-icon">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="20 6 9 17 4 12" />
          </svg>
        </div>
        <h1>Consultation submitted</h1>
        <p>Your consultation has been submitted successfully.</p>
        <p style={{ color: "var(--text-muted)" }}>
          If you do not receive a response from the practice within 48 hours,
          please contact them directly.
        </p>
      </PageShell>
    );
  }

  return null;
}

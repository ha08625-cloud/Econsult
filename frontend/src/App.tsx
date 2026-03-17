import React, { useState, useEffect } from "react";
import DOMPurify from "dompurify";
import {
  getSafetyWarning,
  getAvailability,
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
  PresentationState,
  ContactPreferences,
  ContactMethod,
} from "./types";
import ConditionCombobox from "./ConditionCombobox";
import { GENERAL_CONSULTATION_ID, SIGNPOSTING_PURIFY_CONFIG } from './constants';

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

function initialiseContactPreferences(): ContactPreferences {
  return {
    contact_methods: [],
    email_address: null,
    phone_number: null,
    best_time_to_call: null,
    doctor_preference: "any",
    usual_doctor_name: null,
  };
}

/**
 * UK phone number client-side validation.
 * Strips spaces, checks starts with 07 or +44, length 10–13 digits.
 */
function isValidUkPhone(value: string): boolean {
  const stripped = value.replace(/\s+/g, "");
  if (!/^\+?[\d]+$/.test(stripped)) return false;
  const digitsOnly = stripped.replace(/^\+44/, "0");
  return /^07\d{8,11}$/.test(digitsOnly) || /^0[1-9]\d{8,9}$/.test(digitsOnly);
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
    "SAFETY_WARNING" | "SELECT_CONDITION" | "FREE_TEXT" | "EDIT" | "REVIEW" | "CONTACT" | "DONE"
  >("SAFETY_WARNING");

  // Session state (populated after /form/init)
  const [runtimeId, setRuntimeId] = useState<string | null>(null);
  const [version, setVersion] = useState<number | null>(null);
  const [clientState, setClientState] = useState<ClientStateView | null>(null);
  const [editableAnswers, setEditableAnswers] = useState<Record<string, boolean | string | null> | null>(null);
  const [additionalText, setAdditionalText] = useState<string>("");
  const [safetyMessages, setSafetyMessages] = useState<SafetyMessage[]>([]);

  // Contact preferences state
  const [contactPreferences, setContactPreferences] = useState<ContactPreferences>(
    initialiseContactPreferences()
  );
  // Per-field inline errors for the CONTACT screen
  const [contactErrors, setContactErrors] = useState<Record<string, string>>({});

  // Shared UI state
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [fatalError, setFatalError] = useState<string | null>(null);
  const [screenError, setScreenError] = useState<string | null>(null);

  // Screen 0 state (safety gate)
  const [safetyWarningText, setSafetyWarningText] = useState<string | null>(null);
  const [safetyConfirmed, setSafetyConfirmed] = useState(false);

  // Screen 0 state (availability)
  // null = not yet fetched. Fail-open: if the fetch fails, these stay null
  // and the form proceeds as normal.
  const [availabilityClosedMessage, setAvailabilityClosedMessage] = useState<string | null>(null);
  const [afterHoursNotice, setAfterHoursNotice] = useState<string | null>(null);
  const [practiceIsOpen, setPracticeIsOpen] = useState<boolean | null>(null);

  // Screen 1 state (condition discovery)
  const [conditions, setConditions] = useState<ConditionSummary[] | null>(null);
  const [selectedConditionId, setSelectedConditionId] = useState<string | null>(null);

  // Screen 2 state (presentation framing)
  // No idle state — this value is only rendered inside the FREE_TEXT screen block.
  // Both transitions into FREE_TEXT reset this to "loading" before navigating.
  // If a future developer adds a third path to FREE_TEXT, they must do the same.
  const [presentationState, setPresentationState] = useState<PresentationState>({ status: "loading" });
  // presentationFetchTrigger is a counter whose only purpose is to signal
  // "please re-fetch, even though selectedConditionId has not changed".
  // It is incremented at every navigation boundary into FREE_TEXT and by retryPresentation.
  const [presentationFetchTrigger, setPresentationFetchTrigger] = useState(0);
  const [freeText, setFreeText] = useState<string>("");

  // DONE screen state (populated from /form/finish response)
  const [submittedAfterHours, setSubmittedAfterHours] = useState(false);

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
  // Availability fetch (Screen 0)
  // ---------------------------------
  // Fetched alongside the safety warning. If the fetch fails for any reason
  // (network error, any non-200 response), fail open: the form proceeds as
  // normal with no closed message banner and no after-hours notice.
  // A fetch failure must never lock patients out.

  useEffect(() => {
    if (screen !== "SAFETY_WARNING") return;
    // Only fetch once — if practiceIsOpen has been set, we already fetched.
    if (practiceIsOpen !== null) return;

    let cancelled = false;

    async function fetchAvailability() {
      try {
        const res = await getAvailability();
        if (cancelled) return;
        setPracticeIsOpen(res.is_open);
        setAvailabilityClosedMessage(res.closed_message);
        setAfterHoursNotice(res.after_hours_notice);
      } catch {
        // Fail open — silently ignore any error.
        // The form proceeds as normal.
        if (!cancelled) {
          setPracticeIsOpen(true);
        }
      }
    }

    fetchAvailability();

    return () => { cancelled = true; };
  }, [screen, practiceIsOpen]);

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
  // Presentation fetch (Screen 2)
  // ---------------------------------
  // Fires when selectedConditionId changes or when presentationFetchTrigger
  // is incremented (navigation into FREE_TEXT, or retry).
  //
  // Note: in development with React StrictMode, this effect fires twice on
  // every FREE_TEXT entry. The cancelled flag discards the first result.
  // You will see two network requests in the browser dev tools — this is
  // expected and not a bug.

  useEffect(() => {
    if (selectedConditionId === null) return;

    let cancelled = false;
    // Belt-and-braces: Step 3 already sets loading at the navigation boundary,
    // but this also covers the case where selectedConditionId changes without
    // a screen transition (cannot happen today, but guards future refactors).
    setPresentationState({ status: "loading" });

    async function fetchPresentation() {
      try {
        const res = await getConditionPresentation(selectedConditionId!);
        if (!cancelled) setPresentationState({ status: "success", data: res });
      } catch (e) {
        if (!cancelled) setPresentationState({ status: "error", message: friendlyErrorMessage(e) });
      }
    }

    fetchPresentation();
    return () => { cancelled = true; };
  }, [selectedConditionId, presentationFetchTrigger]);

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
              setPresentationState({ status: "loading" });
              setPresentationFetchTrigger(0);
              setFreeText("");
              setContactPreferences(initialiseContactPreferences());
              setContactErrors({});
              setPracticeIsOpen(null);
              setAvailabilityClosedMessage(null);
              setAfterHoursNotice(null);
              setSubmittedAfterHours(false);
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
    // Practice is closed: is_open is explicitly false (not null, not true).
    const isClosed = practiceIsOpen === false;

    return (
      <PageShell>
        <h1>Before you continue</h1>

        {/* Closed message banner — above safety warning */}
        {isClosed && availabilityClosedMessage && (
          <div
            className="alert alert-warning"
            style={{ marginBottom: "16px" }}
          >
            <strong>This service is currently closed</strong>
            <p style={{ margin: "8px 0 0 0" }}>{availabilityClosedMessage}</p>
          </div>
        )}

        {isClosed && !availabilityClosedMessage && (
          <div
            className="alert alert-warning"
            style={{ marginBottom: "16px" }}
          >
            <strong>This service is currently closed</strong>
          </div>
        )}

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

            {/* After-hours notice — below safety warning, above form controls */}
            {afterHoursNotice && !isClosed && (
              <div
                className="alert alert-info"
                style={{ marginBottom: "16px" }}
              >
                <p style={{ margin: 0 }}>{afterHoursNotice}</p>
              </div>
            )}

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
                disabled={!safetyConfirmed || isClosed}
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
      setPresentationState({ status: "loading" });
      setPresentationFetchTrigger(k => k + 1);
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
                onClick={() => {
                  setPresentationState({ status: "loading" });
                  setPresentationFetchTrigger(k => k + 1);
                  setScreen("FREE_TEXT");
                }}
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

    function retryPresentation() {
      setPresentationState({ status: "loading" });
      setPresentationFetchTrigger(k => k + 1);
    }

    console.log(selectedConditionId)
    if (presentationState.status === "loading") {
      return (
        <PageShell>
          <p className="status-text">Loading...</p>
        </PageShell>
      );
    }

    if (presentationState.status === "error") {
      return (
        <PageShell>
          <h1>Something went wrong</h1>
          <InlineError message={presentationState.message} />
          <div className="btn-row">
            <button
              className="btn btn-secondary"
              onClick={() => setScreen("SELECT_CONDITION")}
            >
              Back
            </button>
            <button
              className="btn btn-primary"
              onClick={retryPresentation}
            >
              Try again
            </button>
          </div>
        </PageShell>
      );
    }

    // status === "success"
    const presentation = presentationState.data;

    return (
      <PageShell>
        <h1>{presentation.label}</h1>

        {presentation.practice_signposting && (
            <div
              className="alert alert-info"
              dangerouslySetInnerHTML={{
                __html: DOMPurify.sanitize(
                  presentation.practice_signposting,
                  SIGNPOSTING_PURIFY_CONFIG
                )
              }}
            />
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
            className="btn btn-secondary"
            disabled={isSubmitting}
            onClick={() => setScreen("SELECT_CONDITION")}
          >
            Back
          </button>
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
                setPresentationState({ status: "loading" });
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
              className="btn btn-secondary"
              disabled={isSubmitting}
              onClick={() => {
                setPresentationState({ status: "loading" });
                setPresentationFetchTrigger(k => k + 1);
                setScreen("FREE_TEXT");
              }}
            >
              Back
            </button>
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
            disabled={hasSafetyBlock}
            onClick={() => {
              setScreenError(null);
              setContactPreferences(initialiseContactPreferences());
              setContactErrors({});
              setScreen("CONTACT");
            }}
          >
            Continue
          </button>
        </div>
      </PageShell>
    );
  }

  // ---------------------------------
  // Screen 5: CONTACT
  // ---------------------------------

  if (screen === "CONTACT") {
    if (runtimeId === null || version === null) {
      setFatalError("Invalid CONTACT state");
      return null;
    }

    // Capture narrowed values as constants so TypeScript can trust them
    // inside nested functions like validateAndSubmit.
    const contactRuntimeId: string = runtimeId;
    const contactVersion: number = version;

    const cp = contactPreferences;
    const methods = cp.contact_methods;
    const wantsPhone = methods.includes("phone");
    const wantsText = methods.includes("text");
    const wantsPhoneOrText = wantsPhone || wantsText;
    const wantsEmail = methods.includes("email");

    function toggleMethod(method: ContactMethod) {
      const next = methods.includes(method)
        ? methods.filter((m) => m !== method)
        : [...methods, method];
      setContactPreferences({ ...cp, contact_methods: next });
      if (contactErrors.contact_methods) {
        setContactErrors({ ...contactErrors, contact_methods: "" });
      }
    }

    function validateAndSubmit() {
      const errors: Record<string, string> = {};

      if (methods.length === 0) {
        errors.contact_methods = "Please select at least one contact method.";
      }

      if (wantsPhoneOrText) {
        const phone = cp.phone_number?.trim() ?? "";
        if (!phone) {
          errors.phone_number = "Please enter a phone number.";
        } else if (!isValidUkPhone(phone)) {
          errors.phone_number =
            "Please enter a valid UK mobile or landline number. We are unable to contact international numbers.";
        }
      }

      if (wantsEmail) {
        const email = cp.email_address?.trim() ?? "";
        if (!email) {
          errors.email_address = "Please enter an email address.";
        } else if (!email.includes("@")) {
          errors.email_address = "Please enter a valid email address.";
        }
      }

      if (cp.doctor_preference === "usual") {
        if (!cp.usual_doctor_name?.trim()) {
          errors.usual_doctor_name = "Please enter your doctor's name.";
        }
      }

      if (Object.keys(errors).length > 0) {
        setContactErrors(errors);
        return;
      }

      // Build clean payload — null out fields that are not relevant
      const cleanPreferences: ContactPreferences = {
        contact_methods: methods,
        email_address: wantsEmail ? (cp.email_address?.trim() || null) : null,
        phone_number: wantsPhoneOrText ? (cp.phone_number?.trim() || null) : null,
        best_time_to_call: wantsPhone ? (cp.best_time_to_call?.trim() || null) : null,
        doctor_preference: cp.doctor_preference,
        usual_doctor_name:
          cp.doctor_preference === "usual" ? (cp.usual_doctor_name?.trim() || null) : null,
      };

      setIsSubmitting(true);
      setScreenError(null);

      finishForm(contactRuntimeId, contactVersion, cleanPreferences)
        .then((res) => {
          setSubmittedAfterHours(res.submitted_after_hours ?? false);
          setScreen("DONE");
        })
        .catch((e) => {
          setScreenError(friendlyErrorMessage(e));
        })
        .finally(() => {
          setIsSubmitting(false);
        });
    }

    return (
      <PageShell>
        <h1>How would you like to be contacted?</h1>

        <div
          style={{
            background: "var(--surface-alt, #f0f4fa)",
            border: "1px solid var(--border, #d0d7e3)",
            borderRadius: "6px",
            padding: "12px 16px",
            marginBottom: "24px",
            fontSize: "14px",
            color: "var(--text-muted)",
          }}
        >
          If you choose email or text message, we aim to respond within 2 working
          days. If you select phone call only, we aim to respond within 5 working
          days.
        </div>

        <div className="field">
          <label>Contact method (select all that apply)</label>
          <div style={{ display: "flex", flexDirection: "column", gap: "10px", marginTop: "8px" }}>
            {(["email", "text", "phone"] as ContactMethod[]).map((method) => {
              const labels: Record<ContactMethod, string> = {
                email: "Email",
                text: "Text message",
                phone: "Phone call",
              };
              return (
                <label
                  key={method}
                  style={{ display: "flex", alignItems: "center", gap: "10px", cursor: "pointer", fontSize: "15px" }}
                >
                  <input
                    type="checkbox"
                    checked={methods.includes(method)}
                    onChange={() => toggleMethod(method)}
                  />
                  {labels[method]}
                </label>
              );
            })}
          </div>
          {contactErrors.contact_methods && (
            <p style={{ color: "var(--danger)", fontSize: "13px", marginTop: "6px" }}>
              {contactErrors.contact_methods}
            </p>
          )}
        </div>

        {wantsPhoneOrText && (
          <div className="field">
            <label htmlFor="contact-phone">Phone number</label>
            <input
              id="contact-phone"
              type="tel"
              value={cp.phone_number ?? ""}
              onChange={(e) => {
                setContactPreferences({ ...cp, phone_number: e.target.value });
                if (contactErrors.phone_number) setContactErrors({ ...contactErrors, phone_number: "" });
              }}
            />
            <p style={{ fontSize: "13px", color: "var(--text-muted)", marginTop: "4px" }}>
              UK numbers only. We are unable to contact international numbers.
            </p>
            {contactErrors.phone_number && (
              <p style={{ color: "var(--danger)", fontSize: "13px", marginTop: "2px" }}>
                {contactErrors.phone_number}
              </p>
            )}
          </div>
        )}

        {wantsEmail && (
          <div className="field">
            <label htmlFor="contact-email">Email address</label>
            <input
              id="contact-email"
              type="email"
              value={cp.email_address ?? ""}
              onChange={(e) => {
                setContactPreferences({ ...cp, email_address: e.target.value });
                if (contactErrors.email_address) setContactErrors({ ...contactErrors, email_address: "" });
              }}
            />
            {contactErrors.email_address && (
              <p style={{ color: "var(--danger)", fontSize: "13px", marginTop: "2px" }}>
                {contactErrors.email_address}
              </p>
            )}
          </div>
        )}

        {wantsPhone && (
          <div className="field">
            <label htmlFor="contact-best-time">Best time to call (optional)</label>
            <input
              id="contact-best-time"
              type="text"
              placeholder="e.g. Mornings before 11am"
              value={cp.best_time_to_call ?? ""}
              onChange={(e) =>
                setContactPreferences({ ...cp, best_time_to_call: e.target.value })
              }
            />
          </div>
        )}

        <div className="field" style={{ marginTop: "24px" }}>
          <label htmlFor="doctor-preference">Which doctor would you prefer to hear from?</label>
          <select
            id="doctor-preference"
            value={cp.doctor_preference}
            onChange={(e) => {
              setContactPreferences({
                ...cp,
                doctor_preference: e.target.value as "any" | "usual",
                usual_doctor_name: null,
              });
              if (contactErrors.usual_doctor_name) {
                setContactErrors({ ...contactErrors, usual_doctor_name: "" });
              }
            }}
            style={{ marginTop: "8px" }}
          >
            <option value="any">Soonest available doctor</option>
            <option value="usual">I would prefer my usual doctor</option>
          </select>
        </div>

        {cp.doctor_preference === "usual" && (
          <div className="field">
            <label htmlFor="usual-doctor-name">Please enter your doctor's name</label>
            <input
              id="usual-doctor-name"
              type="text"
              value={cp.usual_doctor_name ?? ""}
              onChange={(e) => {
                setContactPreferences({ ...cp, usual_doctor_name: e.target.value });
                if (contactErrors.usual_doctor_name) {
                  setContactErrors({ ...contactErrors, usual_doctor_name: "" });
                }
              }}
            />
            {contactErrors.usual_doctor_name && (
              <p style={{ color: "var(--danger)", fontSize: "13px", marginTop: "2px" }}>
                {contactErrors.usual_doctor_name}
              </p>
            )}
          </div>
        )}

        {screenError && <InlineError message={screenError} />}

        <div className="btn-row">
          <button
            className="btn btn-secondary"
            disabled={isSubmitting}
            onClick={() => setScreen("REVIEW")}
          >
            Back
          </button>

          <button
            className="btn btn-primary"
            disabled={isSubmitting}
            onClick={validateAndSubmit}
          >
            {isSubmitting ? "Submitting\u2026" : "Submit"}
          </button>
        </div>
      </PageShell>
    );
  }

  // ---------------------------------
  // Screen 6: DONE
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
        {submittedAfterHours ? (
          <p style={{ color: "var(--text-muted)" }}>
            The practice is now closed — your submission will be reviewed on the next working day.
          </p>
        ) : (
          <p style={{ color: "var(--text-muted)" }}>
            If you do not hear back from the practice within the timeframe indicated,
            please contact them directly.
          </p>
        )}
      </PageShell>
    );
  }

  return null;
}

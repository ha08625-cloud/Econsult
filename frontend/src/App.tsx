import { useState, useEffect } from "react";
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
import { GENERAL_CONSULTATION_ID, SIGNPOSTING_PURIFY_CONFIG } from './constants';
import { PageShell, InlineError } from "./layout";
import {
  initialiseEditableAnswers,
  initialiseContactPreferences,
  isValidUkPhone,
} from "./helpers";
import DoneScreen from "./screens/DoneScreen";
import SafetyWarningScreen from "./screens/SafetyWarningScreen";
import type { SafetyWarningFetchState } from "./screens/SafetyWarningScreen";
import SelectConditionScreen from "./screens/SelectConditionScreen";
import ReviewScreen from "./screens/ReviewScreen";
import EditScreen from "./screens/EditScreen";
import FreeTextScreen from "./screens/FreeTextScreen";

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
  const [safetyFetchError, setSafetyFetchError] = useState<string | null>(null);

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
        if (!cancelled) setSafetyFetchError(friendlyErrorMessage(e));
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

  // RESET CHECKLIST — every useState in App.tsx must appear below.
  // If you add a new useState to App.tsx, add it to this list.
  // When extracting screens in Phase 3: if a state variable moves into
  // a child component, remove it from this list AND from the reset block.
  //
  // screen
  // runtimeId
  // version
  // clientState
  // editableAnswers
  // additionalText
  // safetyMessages
  // contactPreferences
  // contactErrors
  // isSubmitting
  // fatalError
  // screenError
  // safetyWarningText
  // safetyConfirmed
  // availabilityClosedMessage
  // afterHoursNotice
  // practiceIsOpen
  // presentationState         <-- replaces: presentation
  // presentationFetchTrigger  <-- counter, resets to 0 (not null)
  // conditions
  // selectedConditionId
  // freeText
  // submittedAfterHours

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

if (screen === "SAFETY_WARNING") {
  const safetyWarningFetchState: SafetyWarningFetchState =
    safetyFetchError !== null
      ? { status: "error", message: safetyFetchError }
      : safetyWarningText !== null
      ? { status: "success", text: safetyWarningText }
      : { status: "loading" };

  return (
    <SafetyWarningScreen
      safetyWarningFetchState={safetyWarningFetchState}
      safetyConfirmed={safetyConfirmed}
      practiceIsOpen={practiceIsOpen}
      availabilityClosedMessage={availabilityClosedMessage}
      afterHoursNotice={afterHoursNotice}
      onConfirmChange={(confirmed) => setSafetyConfirmed(confirmed)}
      onRetry={() => {
        setSafetyFetchError(null);
        setSafetyWarningText(null);
      }}
      onContinue={() => setScreen("SELECT_CONDITION")}
    />
  );
}

if (screen === "SELECT_CONDITION") {
  return (
    <SelectConditionScreen
      conditions={
        conditions
          ? conditions.filter((c) => c.id !== GENERAL_CONSULTATION_ID)
          : null
      }
      selectedConditionId={selectedConditionId}
      onConditionChange={(newId) => {
        if (newId !== selectedConditionId) {
          setFreeText("");
        }
        setSelectedConditionId(newId);
      }}
      onContinue={() => {
        setPresentationState({ status: "loading" });
        setPresentationFetchTrigger((k) => k + 1);
        setScreen("FREE_TEXT");
      }}
      onBlankForm={() => {
        setSelectedConditionId(GENERAL_CONSULTATION_ID);
        setPresentationState({ status: "loading" });
        setPresentationFetchTrigger((k) => k + 1);
        setScreen("FREE_TEXT");
      }}
    />
  );
}

if (screen === "FREE_TEXT") {
  if (selectedConditionId === null) {
    setFatalError("No condition selected");
    return null;
  }

  return (
    <FreeTextScreen
      presentationState={presentationState}
      freeText={freeText}
      selectedConditionId={selectedConditionId}
      onFreeTextChange={(text) => setFreeText(text)}
      onContinue={(result) => {
        setRuntimeId(result.runtimeId);
        setVersion(result.version);
        setClientState(result.clientState);
        setEditableAnswers(result.editableAnswers);
        setAdditionalText(result.additionalText);
        setScreen("EDIT");
      }}
      onBack={() => setScreen("SELECT_CONDITION")}
      onRetry={() => setPresentationFetchTrigger((k) => k + 1)}
    />
  );
}

  if (screen === "EDIT") {
  if (!clientState || !editableAnswers || runtimeId === null || version === null) {
    setFatalError("Invalid EDIT state");
    return null;
  }

  return (
    <EditScreen
      clientState={clientState}
      editableAnswers={editableAnswers}
      additionalText={additionalText}
      onAnswersChange={(answers) => setEditableAnswers(answers)}
      onAdditionalTextChange={(text) => setAdditionalText(text)}
      onContinue={(result) => {
        setVersion(result.version);
        setClientState(result.clientState);
        setSafetyMessages(result.safetyMessages);
        setEditableAnswers(null);
        setScreen("REVIEW");
      }}
      onBack={() => {
        setPresentationState({ status: "loading" });
        setPresentationFetchTrigger((k) => k + 1);
        setScreen("FREE_TEXT");
      }}
      runtimeId={runtimeId}
      version={version}
    />
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

  if (screen === "DONE") {
  return <DoneScreen submittedAfterHours={submittedAfterHours} />;
}

  return null;
}

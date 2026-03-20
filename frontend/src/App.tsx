import { useState, useEffect } from "react";
import {
  getSafetyWarning,
  getAvailability,
  getConditions,
  getConditionPresentation,
  friendlyErrorMessage,
} from "./api";
import type {
  ClientStateView,
  SafetyMessage,
  ConditionSummary,
  PresentationState,
} from "./types";
import { GENERAL_CONSULTATION_ID } from './constants';
import { PageShell } from "./layout";
import { initialiseEditableAnswers } from "./helpers";
import DoneScreen from "./screens/DoneScreen";
import SafetyWarningScreen from "./screens/SafetyWarningScreen";
import type { SafetyWarningFetchState } from "./screens/SafetyWarningScreen";
import SelectConditionScreen from "./screens/SelectConditionScreen";
import ReviewScreen from "./screens/ReviewScreen";
import EditScreen from "./screens/EditScreen";
import FreeTextScreen from "./screens/FreeTextScreen";
import ContactScreen from "./screens/ContactScreen";

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

  // Shared UI state
  const [fatalError, setFatalError] = useState<string | null>(null);
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
  // When a state variable moves into a child component, remove it from
  // this list AND from the reset block.
  //
  // screen
  // runtimeId
  // version
  // clientState
  // editableAnswers
  // additionalText
  // safetyMessages
  // fatalError
  // safetyFetchError
  // safetyWarningText
  // safetyConfirmed
  // availabilityClosedMessage
  // afterHoursNotice
  // practiceIsOpen
  // presentationState
  // presentationFetchTrigger
  // conditions
  // selectedConditionId
  // freeText

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
              setSafetyFetchError(null);
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
              setPracticeIsOpen(null);
              setAvailabilityClosedMessage(null);
              setAfterHoursNotice(null);
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

  if (screen === "REVIEW") {
    if (!clientState || runtimeId === null || version === null) {
      setFatalError("Invalid REVIEW state");
      return null;
    }

    return (
      <ReviewScreen
        clientState={clientState}
        safetyMessages={safetyMessages}
        onBack={() => {
          setEditableAnswers(initialiseEditableAnswers(clientState));
          setScreen("EDIT");
        }}
        onContinue={() => setScreen("CONTACT")}
      />
    );
  }

  if (screen === "CONTACT") {
    if (runtimeId === null || version === null) {
      setFatalError("Invalid CONTACT state");
      return null;
    }

    return (
      <ContactScreen
        runtimeId={runtimeId}
        version={version}
        onSubmit={() => {
          setScreen("DONE");
        }}
        onBack={() => setScreen("REVIEW")}
      />
    );
  }

  if (screen === "DONE") {
    return <DoneScreen practiceWasClosed={practiceIsOpen === false} />;
  }

  return null;
}

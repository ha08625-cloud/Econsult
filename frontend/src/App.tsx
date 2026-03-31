import { useState, useEffect, useRef } from "react";
import {
  getSafetyWarning,
  getPractice,
  getAvailability,
  getDoctors,
  getConditions,
  getConditionPresentation,
  friendlyErrorMessage,
} from "./api";
import type {
  ClientStateView,
  SafetyMessage,
  ConditionSummary,
  PresentationState,
  PatientDetails,
  SafetyWarningFetchState,
  PracticeNameFetchState,
  ConsultationOutcome,
} from "./types";
import type { PhotoAttachment } from "./uiTypes";
import { GENERAL_CONSULTATION_ID } from './constants';
import { PageShell } from "./layout";
import { initialiseEditableAnswers } from "./helpers";
import DoneScreen from "./screens/DoneScreen";
import SafetyWarningScreen from "./screens/SafetyWarningScreen";
import PatientDetailsScreen from "./screens/PatientDetailsScreen";
import OutcomeScreen from "./screens/OutcomeScreen";
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
    | "SAFETY_WARNING"
    | "PATIENT_DETAILS"
    | "OUTCOME"
    | "SELECT_CONDITION"
    | "FREE_TEXT"
    | "EDIT"
    | "REVIEW"
    | "CONTACT"
    | "DONE"
  >("SAFETY_WARNING");

  // Session state (populated after /form/init)
  const [runtimeId, setRuntimeId] = useState<string | null>(null);
  const [version, setVersion] = useState<number | null>(null);
  const [clientState, setClientState] = useState<ClientStateView | null>(null);
  const [editableAnswers, setEditableAnswers] = useState<Record<string, boolean | string | null> | null>(null);
  const [additionalText, setAdditionalText] = useState<string>("");
  const [safetyMessages, setSafetyMessages] = useState<SafetyMessage[]>([]);

  // Patient details (captured before condition selection — NHS contractual obligation)
  const [patientDetails, setPatientDetails] = useState<PatientDetails | null>(null);

  // Consultation outcome (captured on OUTCOME screen, before SELECT_CONDITION)
  const [consultationOutcome, setConsultationOutcome] = useState<ConsultationOutcome | null>(null);

  // Photo attachments — object URLs in each PhotoAttachment must be revoked
  // when photos are removed or the session ends. See cleanup effects below.
  const [photos, setPhotos] = useState<PhotoAttachment[]>([]);

  // Shared UI state
  const [fatalError, setFatalError] = useState<string | null>(null);

  // Warning dialog shown when patient navigates back from EDIT to FREE_TEXT.
  // Renders as an overlay on top of the EDIT screen so answers are not lost.
  const [showBackWarning, setShowBackWarning] = useState(false);

  // Screen 0 state (safety warning fetch)
  // Single discriminated union — replaces the previous safetyWarningText + safetyFetchError pair.
  // Guard: if status === "success", do not re-fetch.
  // Retry: reset to { status: "loading" } to trigger a new fetch.
  const [safetyWarningFetchState, setSafetyWarningFetchState] = useState<SafetyWarningFetchState>(
    { status: "loading" }
  );

  // Screen 0 state (practice name fetch)
  // Fail-closed: the Continue button is disabled until this reaches "success".
  // Guard: if status === "success", do not re-fetch.
  // Retry: reset to { status: "loading" } to trigger a new fetch.
  const [practiceNameFetchState, setPracticeNameFetchState] = useState<PracticeNameFetchState>(
    { status: "loading" }
  );

  // Screen 0 state (safety gate)
  const [safetyConfirmed, setSafetyConfirmed] = useState(false);

  // Screen 0 state (availability)
  // null = not yet fetched. Fail-open: if the fetch fails, these stay null
  // and the form proceeds as normal.
  const [availabilityClosedMessage, setAvailabilityClosedMessage] = useState<string | null>(null);
  const [afterHoursNotice, setAfterHoursNotice] = useState<string | null>(null);
  const [practiceIsOpen, setPracticeIsOpen] = useState<boolean | null>(null);

  // Screen 0 state (doctor list)
  // Fail-open: if the fetch fails, stays as an empty array.
  // An empty array causes ContactScreen to show only the free text fallback.
  const [doctors, setDoctors] = useState<string[]>([]);
  // null = not yet attempted. false = fetch done (success or failure).
  const [doctorsFetched, setDoctorsFetched] = useState<boolean>(false);

  // Screen 2 state (condition discovery)
  const [conditions, setConditions] = useState<ConditionSummary[] | null>(null);
  const [selectedConditionId, setSelectedConditionId] = useState<string | null>(null);

  // Screen 3 state (presentation framing)
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
  // Photo URL cleanup
  // ---------------------------------
  // A ref is used here so the unmount cleanup can see the latest photos value.
  // The cleanup closure would otherwise capture the initial empty array.

  const photosRef = useRef<PhotoAttachment[]>([]);

  useEffect(() => {
    photosRef.current = photos;
  }, [photos]);

  useEffect(() => {
    return () => {
      photosRef.current.forEach((p) => URL.revokeObjectURL(p.previewUrl));
    };
  }, []);

  // ---------------------------------
  // Safety warning fetch (Screen 0)
  // ---------------------------------

  useEffect(() => {
    if (screen !== "SAFETY_WARNING") return;
    if (safetyWarningFetchState.status === "success") return;

    let cancelled = false;

    async function fetchWarning() {
      try {
        const res = await getSafetyWarning();
        if (!cancelled) setSafetyWarningFetchState({ status: "success", text: res.universal_safety_warning });
      } catch (e) {
        if (!cancelled) setSafetyWarningFetchState({ status: "error", message: friendlyErrorMessage(e) });
      }
    }

    fetchWarning();

    return () => { cancelled = true; };
  }, [screen, safetyWarningFetchState]);

  // ---------------------------------
  // Practice name fetch (Screen 0)
  // ---------------------------------
  // Fail-closed: the patient cannot proceed past SafetyWarningScreen until
  // this fetch succeeds. A failure shows an inline error with a retry button.

  useEffect(() => {
    if (screen !== "SAFETY_WARNING") return;
    if (practiceNameFetchState.status === "success") return;

    let cancelled = false;

    async function fetchPractice() {
      try {
        const res = await getPractice();
        if (!cancelled) setPracticeNameFetchState({ status: "success", name: res.practice_name });
      } catch (e) {
        if (!cancelled) setPracticeNameFetchState({ status: "error", message: friendlyErrorMessage(e) });
      }
    }

    fetchPractice();

    return () => { cancelled = true; };
  }, [screen, practiceNameFetchState]);

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
        if (!cancelled) {
          setPracticeIsOpen(res.is_open);
          setAvailabilityClosedMessage(res.closed_message);
          setAfterHoursNotice(res.after_hours_notice);
        }
      } catch {
        // Fail open — do not update practiceIsOpen so the guard above will
        // not re-trigger, but treat the practice as open.
        if (!cancelled) setPracticeIsOpen(true);
      }
    }

    fetchAvailability();

    return () => { cancelled = true; };
  }, [screen, practiceIsOpen]);

  // ---------------------------------
  // Doctor list fetch (Screen 0)
  // ---------------------------------
  // Fetched once on Screen 0. Fail-open: an error leaves doctors as [].

  useEffect(() => {
    if (screen !== "SAFETY_WARNING") return;
    if (doctorsFetched) return;

    let cancelled = false;

    async function fetchDoctors() {
      try {
        const res = await getDoctors();
        if (!cancelled) setDoctors(res.doctors ?? []);
      } catch {
        // Fail open — doctors stays as [].
      } finally {
        if (!cancelled) setDoctorsFetched(true);
      }
    }

    fetchDoctors();

    return () => { cancelled = true; };
  }, [screen, doctorsFetched]);

  // ---------------------------------
  // Condition list fetch (Screen 2)
  // ---------------------------------

  useEffect(() => {
    if (screen !== "SELECT_CONDITION") return;
    if (conditions !== null) return;

    let cancelled = false;

    async function fetchConditions() {
      try {
        const res = await getConditions();
        if (!cancelled) setConditions(res.conditions);
      } catch (e) {
        if (!cancelled) setFatalError(friendlyErrorMessage(e));
      }
    }

    fetchConditions();

    return () => { cancelled = true; };
  }, [screen, conditions]);

  // ---------------------------------
  // Presentation fetch (Screen 3)
  // ---------------------------------

  useEffect(() => {
    if (screen !== "FREE_TEXT") return;
    if (selectedConditionId === null) return;

    let cancelled = false;

    // Always reset to loading at the start of this effect. This covers the case
    // where the effect fires due to presentationFetchTrigger incrementing during
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
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedConditionId, presentationFetchTrigger]);

  // ---------------------------------
  // Derived values
  // ---------------------------------

  const practiceName =
    practiceNameFetchState.status === "success" ? practiceNameFetchState.name : null;

  // ---------------------------------
  // State checklist
  // ---------------------------------
  // Every useState in this file must appear in this list AND in the reset block.
  //
  // screen
  // runtimeId
  // version
  // clientState
  // editableAnswers
  // additionalText
  // safetyMessages
  // patientDetails
  // consultationOutcome
  // photos
  // fatalError
  // showBackWarning
  // safetyWarningFetchState
  // practiceNameFetchState
  // safetyConfirmed
  // availabilityClosedMessage
  // afterHoursNotice
  // practiceIsOpen
  // doctors
  // doctorsFetched
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
              // Revoke photo object URLs before clearing state.
              photos.forEach((p) => URL.revokeObjectURL(p.previewUrl));
              setFatalError(null);
              setScreen("SAFETY_WARNING");
              setSafetyWarningFetchState({ status: "loading" });
              setPracticeNameFetchState({ status: "loading" });
              setSafetyConfirmed(false);
              setRuntimeId(null);
              setVersion(null);
              setClientState(null);
              setEditableAnswers(null);
              setAdditionalText("");
              setSafetyMessages([]);
              setPatientDetails(null);
              setConsultationOutcome(null);
              setPhotos([]);
              setShowBackWarning(false);
              setConditions(null);
              setSelectedConditionId(null);
              setPresentationState({ status: "loading" });
              setPresentationFetchTrigger(0);
              setFreeText("");
              setPracticeIsOpen(null);
              setAvailabilityClosedMessage(null);
              setAfterHoursNotice(null);
              setDoctors([]);
              setDoctorsFetched(false);
            }}
          >
            Try again
          </button>
        </div>
      </PageShell>
    );
  }

  if (screen === "SAFETY_WARNING") {
    return (
      <SafetyWarningScreen
        safetyWarningFetchState={safetyWarningFetchState}
        practiceNameFetchState={practiceNameFetchState}
        safetyConfirmed={safetyConfirmed}
        practiceIsOpen={practiceIsOpen}
        availabilityClosedMessage={availabilityClosedMessage}
        afterHoursNotice={afterHoursNotice}
        onConfirmChange={(confirmed) => setSafetyConfirmed(confirmed)}
        onRetry={() => setSafetyWarningFetchState({ status: "loading" })}
        onPracticeRetry={() => setPracticeNameFetchState({ status: "loading" })}
        onContinue={() => setScreen("PATIENT_DETAILS")}
      />
    );
  }

  if (screen === "PATIENT_DETAILS") {
    return (
      <PatientDetailsScreen
        practiceName={practiceName}
        onContinue={(details) => {
          setPatientDetails(details);
          setScreen("OUTCOME");
        }}
        onBack={() => setScreen("SAFETY_WARNING")}
      />
    );
  }

  if (screen === "OUTCOME") {
    return (
      <OutcomeScreen
        practiceName={practiceName}
        onContinue={(outcome) => {
          setConsultationOutcome(outcome);
          setScreen("SELECT_CONDITION");
        }}
        onBack={() => setScreen("PATIENT_DETAILS")}
      />
    );
  }

  if (screen === "SELECT_CONDITION") {
    return (
      <SelectConditionScreen
        practiceName={practiceName}
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
        practiceName={practiceName}
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
      <>
        {showBackWarning && (
          <div
            style={{
              position: "fixed",
              inset: 0,
              background: "rgba(0,0,0,0.45)",
              zIndex: 100,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <div
              style={{
                background: "var(--surface, #fff)",
                border: "1px solid var(--border, #d0d7e3)",
                borderRadius: "8px",
                padding: "24px",
                maxWidth: "400px",
                width: "90%",
              }}
            >
              <p style={{ marginBottom: "20px" }}>
                If you have attached photos, they will be lost and may need to be re-uploaded.
              </p>
              <div className="btn-row">
                <button
                  className="btn btn-secondary"
                  onClick={() => setShowBackWarning(false)}
                >
                  Stay on this page
                </button>
                <button
                  className="btn btn-primary"
                  onClick={() => {
                    photos.forEach((p) => URL.revokeObjectURL(p.previewUrl));
                    setPhotos([]);
                    setShowBackWarning(false);
                    setPresentationState({ status: "loading" });
                    setPresentationFetchTrigger((k) => k + 1);
                    setScreen("FREE_TEXT");
                  }}
                >
                  Go back
                </button>
              </div>
            </div>
          </div>
        )}
        <EditScreen
          practiceName={practiceName}
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
          onBack={() => setShowBackWarning(true)}
          runtimeId={runtimeId}
          version={version}
          photos={photos}
          onPhotosChange={(updated) => setPhotos(updated)}
        />
      </>
    );
  }

  if (screen === "REVIEW") {
    if (!clientState || runtimeId === null || version === null) {
      setFatalError("Invalid REVIEW state");
      return null;
    }

    return (
      <ReviewScreen
        practiceName={practiceName}
        clientState={clientState}
        safetyMessages={safetyMessages}
        photos={photos}
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
    if (patientDetails === null) {
      setFatalError("Patient details missing at submission");
      return null;
    }
    if (consultationOutcome === null) {
      setFatalError("Consultation outcome missing at submission");
      return null;
    }

    return (
      <ContactScreen
        practiceName={practiceName}
        runtimeId={runtimeId}
        version={version}
        patientDetails={patientDetails}
        consultationOutcome={consultationOutcome}
        photos={photos.map((p) => p.file)}
        doctors={doctors}
        onSubmit={() => {
          setScreen("DONE");
        }}
        onBack={() => setScreen("REVIEW")}
      />
    );
  }

  if (screen === "DONE") {
    return (
      <DoneScreen
        practiceName={practiceName}
        practiceWasClosed={practiceIsOpen === false}
      />
    );
  }

  return null;
}
// File path: frontend/src/App.tsx
import { useState, useEffect, useRef } from "react";
import * as Sentry from "@sentry/react";
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
  ConsultationOutcome,
} from "./types";
import type { PhotoAttachment } from "./uiTypes";
import type { PhotoTier } from "./screens/EditScreen";
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

  const [runtimeId, setRuntimeId] = useState<string | null>(null);
  const [version, setVersion] = useState<number | null>(null);
  const [clientState, setClientState] = useState<ClientStateView | null>(null);
  const [editableAnswers, setEditableAnswers] = useState<Record<string, boolean | string | null> | null>(null);
  const [additionalText, setAdditionalText] = useState<string>("");
  const [safetyMessages, setSafetyMessages] = useState<SafetyMessage[]>([]);
  const [patientDetails, setPatientDetails] = useState<PatientDetails | null>(null);
  const [consultationOutcome, setConsultationOutcome] = useState<ConsultationOutcome | null>(null);
  const [photos, setPhotos] = useState<PhotoAttachment[]>([]);
  const [photoTier, setPhotoTier] = useState<PhotoTier | null>(null);
  const [fatalError, setFatalError] = useState<string | null>(null);
  const [showBackWarning, setShowBackWarning] = useState(false);
  const [safetyWarningFetchState, setSafetyWarningFetchState] = useState<SafetyWarningFetchState>({ status: "loading" });
  const [practiceName, setPracticeName] = useState<string | null>(null);
  const [practiceNameFetched, setPracticeNameFetched] = useState<boolean>(false);
  const [safetyConfirmed, setSafetyConfirmed] = useState(false);
  const [availabilityClosedMessage, setAvailabilityClosedMessage] = useState<string | null>(null);
  const [afterHoursNotice, setAfterHoursNotice] = useState<string | null>(null);
  const [practiceIsOpen, setPracticeIsOpen] = useState<boolean | null>(null);
  const [doctors, setDoctors] = useState<string[]>([]);
  const [doctorsFetched, setDoctorsFetched] = useState<boolean>(false);
  const [conditions, setConditions] = useState<ConditionSummary[] | null>(null);
  const [selectedConditionId, setSelectedConditionId] = useState<string | null>(null);
  // The condition the current freeText was actually written against. Distinct
  // from selectedConditionId, which is also nulled transiently while the
  // patient is mid-typing in the combobox (see ConditionCombobox.tsx). Only
  // ever set at the point free text starts being written for a condition:
  // SELECT_CONDITION's onContinue, onBlankForm, and the "Switch condition"
  // confirmation below. Used to tell a genuine condition switch apart from
  // a no-op re-selection of the condition already in progress.
  const [confirmedConditionId, setConfirmedConditionId] = useState<string | null>(null);
  // Holds a candidate condition id while the condition-change warning modal
  // is open, awaiting the patient's choice.
  const [pendingConditionId, setPendingConditionId] = useState<string | null>(null);
  const [showConditionChangeWarning, setShowConditionChangeWarning] = useState(false);
  // Bumped to force ConditionCombobox to remount when "Keep my answer" is
  // chosen, so its displayed text re-syncs to the restored selectedConditionId.
  const [comboboxResetKey, setComboboxResetKey] = useState(0);
  const [presentationState, setPresentationState] = useState<PresentationState>({ status: "loading" });
  const [presentationFetchTrigger, setPresentationFetchTrigger] = useState(0);
  const [freeText, setFreeText] = useState<string>("");

  const photosRef = useRef<PhotoAttachment[]>([]);
  useEffect(() => { photosRef.current = photos; }, [photos]);

  useEffect(() => {
    return () => {
      photosRef.current.forEach((p) => URL.revokeObjectURL(p.previewUrl));
    };
  }, []);

// ---------------------------------
// Scroll to top on screen change
// ---------------------------------
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [screen]);


  function triggerFatalError(errorMsg: string) {
    Sentry.captureMessage(`Fatal UI Error: ${errorMsg}`, "fatal");
    setFatalError(errorMsg);
  }

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

  useEffect(() => {
    if (screen !== "SAFETY_WARNING") return;
    if (practiceNameFetched) return;
    let cancelled = false;
    async function fetchPractice() {
      try {
        const res = await getPractice();
        if (!cancelled) setPracticeName(res.practice_name);
      } catch { /* Fail open - practice name is a cosmetic header value only */ } finally {
        if (!cancelled) setPracticeNameFetched(true);
      }
    }
    fetchPractice();
    return () => { cancelled = true; };
  }, [screen, practiceNameFetched]);

  useEffect(() => {
    if (screen !== "SAFETY_WARNING") return;
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
        if (!cancelled) setPracticeIsOpen(true);
      }
    }
    fetchAvailability();
    return () => { cancelled = true; };
  }, [screen, practiceIsOpen]);

  useEffect(() => {
    if (screen !== "SAFETY_WARNING") return;
    if (doctorsFetched) return;
    let cancelled = false;
    async function fetchDoctors() {
      try {
        const res = await getDoctors();
        if (!cancelled) setDoctors(res.doctors ?? []);
      } catch { /* Fail open */ } finally {
        if (!cancelled) setDoctorsFetched(true);
      }
    }
    fetchDoctors();
    return () => { cancelled = true; };
  }, [screen, doctorsFetched]);

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

  useEffect(() => {
    if (screen !== "FREE_TEXT") return;
    if (selectedConditionId === null) return;
    let cancelled = false;
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
  }, [screen, selectedConditionId, presentationFetchTrigger]);

  if (fatalError) {
    return (
      <PageShell>
        <div className="screen-card">
          <h1>Unable to load the form</h1>
          <p className="error-message">{fatalError}</p>
          <div className="btn-row">
            <button className="btn btn-primary" onClick={() => window.location.reload()}>Try again</button>
          </div>
        </div>
      </PageShell>
    );
  }

  if (screen === "SAFETY_WARNING") {
    return (
      <SafetyWarningScreen
        safetyWarningFetchState={safetyWarningFetchState}
        practiceName={practiceName}
        safetyConfirmed={safetyConfirmed}
        practiceIsOpen={practiceIsOpen}
        availabilityClosedMessage={availabilityClosedMessage}
        afterHoursNotice={afterHoursNotice}
        onConfirmChange={setSafetyConfirmed}
        onRetry={() => setSafetyWarningFetchState({ status: "loading" })}
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
      <>
        {showConditionChangeWarning && (
          <div className="modal-overlay">
            <div className="screen-card" style={{ maxWidth: '400px' }}>
              <p>Switching conditions will clear the answer you've already typed.</p>
              <div className="btn-row">
                <button
                  className="btn btn-secondary"
                  onClick={() => {
                    setShowConditionChangeWarning(false);
                    setPendingConditionId(null);
                    // Restore selectedConditionId to the last confirmed pick —
                    // necessary because it may already have been nulled by
                    // typing before the pending switch was proposed.
                    setSelectedConditionId(confirmedConditionId);
                    setComboboxResetKey((k) => k + 1);
                  }}
                >
                  Keep my answer
                </button>
                <button
                  className="btn btn-primary"
                  onClick={() => {
                    setFreeText("");
                    setSelectedConditionId(pendingConditionId);
                    setConfirmedConditionId(pendingConditionId);
                    setPendingConditionId(null);
                    setShowConditionChangeWarning(false);
                  }}
                >
                  Switch condition
                </button>
              </div>
            </div>
          </div>
        )}
        <SelectConditionScreen
          practiceName={practiceName}
          conditions={conditions ? conditions.filter((c) => c.id !== GENERAL_CONSULTATION_ID) : null}
          selectedConditionId={selectedConditionId}
          comboboxResetKey={comboboxResetKey}
          onConditionChange={(newId) => {
            // Mid-typing (null) or re-confirming the condition the current
            // free text already belongs to: commit directly, nothing to lose.
            if (newId === null || newId === confirmedConditionId) {
              setSelectedConditionId(newId);
              return;
            }
            // Genuinely different condition. Only worth warning about if
            // there is free text written against the previous one to lose.
            if (freeText !== "") {
              setPendingConditionId(newId);
              setShowConditionChangeWarning(true);
              return;
            }
            setSelectedConditionId(newId);
          }}
          onContinue={() => {
            setConfirmedConditionId(selectedConditionId);
            setPresentationState({ status: "loading" });
            setPresentationFetchTrigger((k) => k + 1);
            setScreen("FREE_TEXT");
          }}
          onBlankForm={() => {
            setSelectedConditionId(GENERAL_CONSULTATION_ID);
            setConfirmedConditionId(GENERAL_CONSULTATION_ID);
            setPresentationState({ status: "loading" });
            setPresentationFetchTrigger((k) => k + 1);
            setScreen("FREE_TEXT");
          }}
          onBack={() => setScreen("OUTCOME")}
        />
      </>
    );
  }

  if (screen === "FREE_TEXT") {
    if (selectedConditionId === null) {
      triggerFatalError("No condition selected");
      return null;
    }
    return (
      <FreeTextScreen
        practiceName={practiceName}
        presentationState={presentationState}
        freeText={freeText}
        selectedConditionId={selectedConditionId}
        onFreeTextChange={setFreeText}
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
      triggerFatalError("Invalid EDIT state");
      return null;
    }
    return (
      <>
        {showBackWarning && (
          <div className="modal-overlay">
            <div className="screen-card" style={{ maxWidth: '400px' }}>
              <p>If you have attached photos, they will be lost and may need to be re-uploaded.</p>
              <div className="btn-row">
                <button className="btn btn-secondary" onClick={() => setShowBackWarning(false)}>Stay</button>
                <button className="btn btn-primary" onClick={() => {
                  photos.forEach((p) => URL.revokeObjectURL(p.previewUrl));
                  setPhotos([]);
                  setShowBackWarning(false);
                  setPresentationState({ status: "loading" });
                  setPresentationFetchTrigger((k) => k + 1);
                  setScreen("FREE_TEXT");
                  setPhotoTier(null);
                }}>Go back</button>
              </div>
            </div>
          </div>
        )}
        <EditScreen
          practiceName={practiceName}
          clientState={clientState}
          editableAnswers={editableAnswers}
          additionalText={additionalText}
          onAnswersChange={setEditableAnswers}
          onAdditionalTextChange={setAdditionalText}
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
          onPhotosChange={setPhotos}
          photoTier={photoTier}
          onPhotoTierChange={setPhotoTier}
        />
      </>
    );
  }

  if (screen === "REVIEW") {
    if (!clientState || runtimeId === null || version === null) {
      triggerFatalError("Invalid REVIEW state");
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
    if (runtimeId === null || version === null || patientDetails === null || consultationOutcome === null) {
      triggerFatalError("State missing at submission");
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
        photoTier={photoTier}
        doctors={doctors}
        onSubmit={() => setScreen("DONE")}
        onBack={() => setScreen("REVIEW")}
      />
    );
  }

  if (screen === "DONE") {
    return <DoneScreen practiceName={practiceName} practiceWasClosed={practiceIsOpen === false} />;
  }

  return null;
}

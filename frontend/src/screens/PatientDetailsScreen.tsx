import { useState } from "react";
import { PageShell } from "../layout";
import type { PatientDetails, DateOfBirth } from "../types";

interface PatientDetailsScreenProps {
  practiceName: string | null;
  onContinue: (details: PatientDetails) => void;
  onBack: () => void;
}

// Basic UK postcode format. Validates format only — does not verify the
// postcode exists or is currently in use.
const UK_POSTCODE_REGEX = /^[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}$/i;

// Returns true if the string contains only digit characters (and is non-empty).
function isDigitsOnly(value: string): boolean {
  return /^\d+$/.test(value);
}

function initialiseDetails(): PatientDetails {
  return {
    patient_for: "me",
    first_name: "",
    last_name: "",
    date_of_birth: { day: "", month: "", year: "" },
    postcode: "",
    submitter_name: "",
    submitter_relationship: "",
  };
}

export default function PatientDetailsScreen({
  practiceName,
  onContinue,
  onBack,
}: PatientDetailsScreenProps) {
  const [details, setDetails] = useState<PatientDetails>(initialiseDetails());
  const [errors, setErrors] = useState<Record<string, string>>({});

  const forSomeoneElse = details.patient_for === "someone_else";

  function setDob(field: keyof DateOfBirth, value: string) {
    setDetails((prev) => ({
      ...prev,
      date_of_birth: { ...prev.date_of_birth, [field]: value },
    }));
    if (errors[`dob_${field}`] || errors.dob) {
      setErrors((prev) => {
        const next = { ...prev };
        delete next[`dob_${field}`];
        delete next.dob;
        return next;
      });
    }
  }

  function setField(key: keyof PatientDetails, value: string) {
    setDetails((prev) => ({ ...prev, [key]: value }));
    if (errors[key]) {
      setErrors((prev) => {
        const next = { ...prev };
        delete next[key];
        return next;
      });
    }
  }

  function setPatientFor(value: "me" | "someone_else") {
    setDetails((prev) => ({ ...prev, patient_for: value }));
    // Clear submitter errors when switching away from "someone_else"
    if (value === "me") {
      setErrors((prev) => {
        const next = { ...prev };
        delete next.submitter_name;
        delete next.submitter_relationship;
        return next;
      });
    }
  }

  function validate(): boolean {
    const next: Record<string, string> = {};

    if (!details.first_name.trim()) {
      next.first_name = "Please enter the patient's first name.";
    }
    if (!details.last_name.trim()) {
      next.last_name = "Please enter the patient's last name.";
    }

    const { day, month, year } = details.date_of_birth;

    if (!day.trim() || !month.trim() || !year.trim()) {
      next.dob = "Please enter a complete date of birth.";
    } else if (!isDigitsOnly(day) || !isDigitsOnly(month) || !isDigitsOnly(year)) {
      next.dob = "Date of birth must contain numbers only.";
    } else {
      // Numeric validation passed — check it forms a real calendar date
      const d = parseInt(day, 10);
      const m = parseInt(month, 10);
      const y = parseInt(year, 10);
      const assembled = new Date(y, m - 1, d);
      const isReal =
        assembled.getFullYear() === y &&
        assembled.getMonth() === m - 1 &&
        assembled.getDate() === d;

      if (!isReal) {
        next.dob = "Please enter a valid date of birth.";
      } else if (assembled > new Date()) {
        next.dob = "Date of birth cannot be in the future.";
      }
    }

    if (!details.postcode.trim()) {
      next.postcode = "Please enter a postcode.";
    } else if (!UK_POSTCODE_REGEX.test(details.postcode.trim())) {
      next.postcode = "Please enter a valid UK postcode.";
    }

    if (forSomeoneElse) {
      if (!details.submitter_name?.trim()) {
        next.submitter_name = "Please enter your name.";
      }
      if (!details.submitter_relationship?.trim()) {
        next.submitter_relationship = "Please enter your relationship to the patient.";
      }
    }

    if (Object.keys(next).length > 0) {
      setErrors(next);
      return false;
    }
    return true;
  }

  function handleContinue() {
    if (!validate()) return;

    // Build a clean payload. Omit submitter fields entirely when not applicable
    // rather than sending empty strings, so the backend allowlist check is clean.
    const clean: PatientDetails = {
      patient_for: details.patient_for,
      first_name: details.first_name.trim(),
      last_name: details.last_name.trim(),
      date_of_birth: {
        day: details.date_of_birth.day.trim(),
        month: details.date_of_birth.month.trim(),
        year: details.date_of_birth.year.trim(),
      },
      postcode: details.postcode.trim(),
      ...(forSomeoneElse && {
        submitter_name: details.submitter_name!.trim(),
        submitter_relationship: details.submitter_relationship!.trim(),
      }),
    };

    onContinue(clean);
  }

  return (
    <PageShell practiceName={practiceName}>
      <h1>About the patient</h1>
      <p style={{ marginBottom: "24px", color: "var(--text-muted)", fontSize: "15px" }}>
        We need a few details before you continue.
      </p>

      {/* Who is this for */}
      <div className="field">
        <label>Who is this consultation for?</label>
        <div style={{ display: "flex", flexDirection: "column", gap: "10px", marginTop: "8px" }}>
          {(["me", "someone_else"] as const).map((val) => {
            const label = val === "me" ? "Myself" : "Someone else";
            return (
              <label
                key={val}
                style={{ display: "flex", alignItems: "center", gap: "10px", cursor: "pointer", fontSize: "15px" }}
              >
                <input
                  type="radio"
                  name="patient_for"
                  value={val}
                  checked={details.patient_for === val}
                  onChange={() => setPatientFor(val)}
                />
                {label}
              </label>
            );
          })}
        </div>
      </div>

      {/* Patient name */}
      <div className="field">
        <label htmlFor="first-name">
          {forSomeoneElse ? "Patient's first name" : "First name"}
        </label>
        <input
          id="first-name"
          type="text"
          value={details.first_name}
          onChange={(e) => setField("first_name", e.target.value)}
        />
        {errors.first_name && (
          <p style={{ color: "var(--danger)", fontSize: "13px", marginTop: "4px" }}>
            {errors.first_name}
          </p>
        )}
      </div>

      <div className="field">
        <label htmlFor="last-name">
          {forSomeoneElse ? "Patient's last name" : "Last name"}
        </label>
        <input
          id="last-name"
          type="text"
          value={details.last_name}
          onChange={(e) => setField("last_name", e.target.value)}
        />
        {errors.last_name && (
          <p style={{ color: "var(--danger)", fontSize: "13px", marginTop: "4px" }}>
            {errors.last_name}
          </p>
        )}
      </div>

      {/* Date of birth */}
      <div className="field">
        <label>
          {forSomeoneElse ? "Patient's date of birth" : "Date of birth"}
        </label>
        <div style={{ display: "flex", gap: "12px", marginTop: "8px" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
            <label htmlFor="dob-day" style={{ fontSize: "13px", color: "var(--text-muted)" }}>Day</label>
            <input
              id="dob-day"
              type="text"
              inputMode="numeric"
              maxLength={2}
              placeholder="DD"
              value={details.date_of_birth.day}
              onChange={(e) => setDob("day", e.target.value)}
              style={{ width: "60px" }}
            />
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
            <label htmlFor="dob-month" style={{ fontSize: "13px", color: "var(--text-muted)" }}>Month</label>
            <input
              id="dob-month"
              type="text"
              inputMode="numeric"
              maxLength={2}
              placeholder="MM"
              value={details.date_of_birth.month}
              onChange={(e) => setDob("month", e.target.value)}
              style={{ width: "60px" }}
            />
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
            <label htmlFor="dob-year" style={{ fontSize: "13px", color: "var(--text-muted)" }}>Year</label>
            <input
              id="dob-year"
              type="text"
              inputMode="numeric"
              maxLength={4}
              placeholder="YYYY"
              value={details.date_of_birth.year}
              onChange={(e) => setDob("year", e.target.value)}
              style={{ width: "80px" }}
            />
          </div>
        </div>
        {errors.dob && (
          <p style={{ color: "var(--danger)", fontSize: "13px", marginTop: "6px" }}>
            {errors.dob}
          </p>
        )}
      </div>

      {/* Postcode */}
      <div className="field">
        <label htmlFor="postcode">
          {forSomeoneElse ? "Patient's postcode" : "Postcode"}
        </label>
        <input
          id="postcode"
          type="text"
          value={details.postcode}
          onChange={(e) => setField("postcode", e.target.value)}
          style={{ textTransform: "uppercase", width: "160px" }}
        />
        {errors.postcode && (
          <p style={{ color: "var(--danger)", fontSize: "13px", marginTop: "4px" }}>
            {errors.postcode}
          </p>
        )}
      </div>

      {/* Submitter fields — only when submitting on behalf of someone else */}
      {forSomeoneElse && (
        <>
          <div className="field">
            <label htmlFor="submitter-name">Your name</label>
            <input
              id="submitter-name"
              type="text"
              value={details.submitter_name ?? ""}
              onChange={(e) => setField("submitter_name", e.target.value)}
            />
            {errors.submitter_name && (
              <p style={{ color: "var(--danger)", fontSize: "13px", marginTop: "4px" }}>
                {errors.submitter_name}
              </p>
            )}
          </div>

          <div className="field">
            <label htmlFor="submitter-relationship">Your relationship to the patient</label>
            <input
              id="submitter-relationship"
              type="text"
              placeholder="e.g. parent, carer, spouse"
              value={details.submitter_relationship ?? ""}
              onChange={(e) => setField("submitter_relationship", e.target.value)}
            />
            {errors.submitter_relationship && (
              <p style={{ color: "var(--danger)", fontSize: "13px", marginTop: "4px" }}>
                {errors.submitter_relationship}
              </p>
            )}
          </div>
        </>
      )}

      <div className="btn-row">
        <button className="btn btn-secondary" onClick={onBack}>
          Back
        </button>
        <button className="btn btn-primary" onClick={handleContinue}>
          Continue
        </button>
      </div>
    </PageShell>
  );
}
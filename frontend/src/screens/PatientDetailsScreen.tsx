import { useState, useRef, ChangeEvent } from "react";
import { PageShell } from "../layout";
import type { PatientDetails, Gender } from "../types";

interface PatientDetailsScreenProps {
  practiceName: string | null;
  onContinue: (details: PatientDetails) => void;
  onBack: () => void;
}

const UK_POSTCODE_REGEX = /^[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}$/i;

function isDigitsOnly(value: string): boolean {
  return /^\d+$/.test(value);
}

function isValidNhsNumber(value: string): boolean {
  const stripped = value.replace(/\s/g, "");
  return /^\d{10}$/.test(stripped);
}

/**
 * Strips non-digits and injects spaces after the 3rd and 6th digits
 * to match the standard NHS 3-3-4 format (e.g., 485 777 3456).
 */
function formatNhsNumber(value: string): string {
  const digits = value.replace(/\D/g, "").slice(0, 10);
  if (digits.length > 6) {
    return `${digits.slice(0, 3)} ${digits.slice(3, 6)} ${digits.slice(6)}`;
  }
  if (digits.length > 3) {
    return `${digits.slice(0, 3)} ${digits.slice(3)}`;
  }
  return digits;
}

interface LocalPatientDetails extends Omit<PatientDetails, "gender"> {
  gender: Gender | null;
}

function initialiseDetails(): LocalPatientDetails {
  return {
    patient_for: "me",
    first_name: "",
    last_name: "",
    date_of_birth: { day: "", month: "", year: "" },
    postcode: "",
    gender: null,
    preferred_name: "",
    nhs_number: "",
    submitter_name: "",
    submitter_relationship: "",
  };
}

const GENDER_OPTIONS: { value: Gender; label: string }[] = [
  { value: "male", label: "Male" },
  { value: "female", label: "Female" },
  { value: "other", label: "Other" },
  { value: "prefer_not_to_say", label: "I'd rather not say" },
];

export default function PatientDetailsScreen({
  practiceName,
  onContinue,
  onBack,
}: PatientDetailsScreenProps) {
  const [details, setDetails] = useState<LocalPatientDetails>(initialiseDetails());
  const [errors, setErrors] = useState<Record<string, string>>({});

  // Refs for auto-tabbing DOB fields
  const monthRef = useRef<HTMLInputElement>(null);
  const yearRef = useRef<HTMLInputElement>(null);

  const forSomeoneElse = details.patient_for === "someone_else";

  function setField(key: keyof LocalPatientDetails, value: any) {
    setDetails((prev) => ({ ...prev, [key]: value }));
    if (errors[key] || (key.startsWith('dob') && errors.dob)) {
      setErrors((prev) => {
        const next = { ...prev };
        delete next[key];
        if (key.startsWith('dob')) delete next.dob;
        return next;
      });
    }
  }

  function handleDobChange(part: 'day' | 'month' | 'year', value: string) {
    // Input Guard: Only allow numbers and limit lengths
    const cleanVal = value.replace(/\D/g, "").slice(0, part === 'year' ? 4 : 2);
    
    const newDob = { ...details.date_of_birth, [part]: cleanVal };
    setField("date_of_birth", newDob);

    // Auto-tabbing logic
    if (cleanVal.length === 2) {
      if (part === 'day') {
        monthRef.current?.focus();
      } else if (part === 'month') {
        yearRef.current?.focus();
      }
    }
  }

  function validate(): boolean {
    const next: Record<string, string> = {};

    if (!details.first_name.trim()) next.first_name = "Enter first name.";
    if (!details.last_name.trim()) next.last_name = "Enter last name.";

    const { day, month, year } = details.date_of_birth;
    if (!day.trim() || !month.trim() || !year.trim()) {
      next.dob = "Enter a complete date of birth.";
    } else if (!isDigitsOnly(day) || !isDigitsOnly(month) || !isDigitsOnly(year)) {
      next.dob = "Use numbers only.";
    } else {
      const d = parseInt(day, 10);
      const m = parseInt(month, 10);
      const y = parseInt(year, 10);
      const assembled = new Date(y, m - 1, d);
      const isReal = assembled.getFullYear() === y && assembled.getMonth() === m - 1 && assembled.getDate() === d;

      if (!isReal) next.dob = "Enter a valid date.";
      else if (assembled > new Date()) next.dob = "Cannot be in the future.";
    }

    if (!details.postcode.trim()) next.postcode = "Enter a postcode.";
    else if (!UK_POSTCODE_REGEX.test(details.postcode.trim())) next.postcode = "Enter a valid UK postcode.";

    if (details.gender === null) next.gender = "Select a gender.";

    const nhsRaw = details.nhs_number ?? "";
    if (nhsRaw.trim() !== "" && !isValidNhsNumber(nhsRaw)) {
      next.nhs_number = "Enter a valid 10-digit NHS number.";
    }

    if (forSomeoneElse) {
      if (!details.submitter_name?.trim()) next.submitter_name = "Enter your name.";
      if (!details.submitter_relationship?.trim()) next.submitter_relationship = "Enter relationship.";
    }

    if (Object.keys(next).length > 0) {
      setErrors(next);
      return false;
    }
    return true;
  }

  function handleContinue() {
    if (!validate()) return;
    const nhsStripped = (details.nhs_number ?? "").replace(/\s/g, "");
    const clean: PatientDetails = {
      ...details,
      first_name: details.first_name.trim(),
      last_name: details.last_name.trim(),
      gender: details.gender as Gender,
      nhs_number: nhsStripped || undefined,
    } as PatientDetails;
    onContinue(clean);
  }

  return (
    <PageShell practiceName={practiceName}>
      <h1>About the patient</h1>
      <p className="screen-description">We need a few details before you continue.</p>

      {/* 1. Ownership Section */}
      <div className={`field ${errors.patient_for ? "has-error" : ""}`}>
        <label>Who is this consultation for?</label>
        <div className="selection-grid">
          {(["me", "someone_else"] as const).map((val) => (
            <label key={val} className={`selection-card ${details.patient_for === val ? "selected" : ""}`}>
              <input
                type="radio"
                name="patient_for"
                checked={details.patient_for === val}
                onChange={() => setField("patient_for", val)}
              />
              <span className="selection-label">{val === "me" ? "Myself" : "Someone else"}</span>
            </label>
          ))}
        </div>
      </div>

      {/* 2. Identity Section */}
      <div className="form-section">
        <div className={`field ${errors.first_name ? "has-error" : ""}`}>
          <label htmlFor="first-name">{forSomeoneElse ? "Patient's first name" : "First name"}</label>
          <input id="first-name" type="text" value={details.first_name} onChange={(e) => setField("first_name", e.target.value)} />
          {errors.first_name && <p className="error-message">{errors.first_name}</p>}
        </div>

        <div className={`field ${errors.last_name ? "has-error" : ""}`}>
          <label htmlFor="last-name">{forSomeoneElse ? "Patient's last name" : "Last name"}</label>
          <input id="last-name" type="text" value={details.last_name} onChange={(e) => setField("last_name", e.target.value)} />
          {errors.last_name && <p className="error-message">{errors.last_name}</p>}
        </div>

        <div className="field">
          <label htmlFor="preferred-name">
            Preferred name <span style={{ fontWeight: 'normal', color: 'var(--text-muted)' }}>(optional)</span>
          </label>
          <input id="preferred-name" type="text" value={details.preferred_name ?? ""} onChange={(e) => setField("preferred_name", e.target.value)} />
        </div>
      </div>

      {/* 3. Biological & Date Info */}
      <div className="form-section">
        <div className={`field ${errors.gender ? "has-error" : ""}`}>
          <label>{forSomeoneElse ? "Patient's gender" : "Gender"}</label>
          <div className="selection-grid">
            {GENDER_OPTIONS.map(({ value, label }) => (
              <label key={value} className={`selection-card ${details.gender === value ? "selected" : ""}`}>
                <input type="radio" name="gender" checked={details.gender === value} onChange={() => setField("gender", value)} />
                <span className="selection-label">{label}</span>
              </label>
            ))}
          </div>
          {errors.gender && <p className="error-message">{errors.gender}</p>}
        </div>

        <div className={`field ${errors.dob ? "has-error" : ""}`}>
          <label>{forSomeoneElse ? "Patient's date of birth" : "Date of birth"}</label>
          <div className="dob-inputs">
            <div className="dob-field">
              <label htmlFor="dob-day">Day</label>
              <input
                id="dob-day"
                type="text"
                inputMode="numeric"
                placeholder="DD"
                style={{ width: '60px' }}
                value={details.date_of_birth.day}
                onChange={(e) => handleDobChange('day', e.target.value)}
              />
            </div>
            <div className="dob-field">
              <label htmlFor="dob-month">Month</label>
              <input
                id="dob-month"
                ref={monthRef}
                type="text"
                inputMode="numeric"
                placeholder="MM"
                style={{ width: '60px' }}
                value={details.date_of_birth.month}
                onChange={(e) => handleDobChange('month', e.target.value)}
              />
            </div>
            <div className="dob-field">
              <label htmlFor="dob-year">Year</label>
              <input
                id="dob-year"
                ref={yearRef}
                type="text"
                inputMode="numeric"
                placeholder="YYYY"
                style={{ width: '80px' }}
                value={details.date_of_birth.year}
                onChange={(e) => handleDobChange('year', e.target.value)}
              />
            </div>
          </div>
          {errors.dob && <p className="error-message">{errors.dob}</p>}
        </div>
      </div>

      {/* 4. Administrative Info */}
      <div className="form-section">
        <div className={`field ${errors.postcode ? "has-error" : ""}`}>
          <label htmlFor="postcode">{forSomeoneElse ? "Patient's postcode" : "Postcode"}</label>
          <input 
            id="postcode" 
            type="text" 
            style={{ width: '160px', textTransform: 'uppercase' }} 
            value={details.postcode} 
            onChange={(e) => setField("postcode", e.target.value.toUpperCase())} 
          />
          {errors.postcode && <p className="error-message">{errors.postcode}</p>}
        </div>

        <div className={`field ${errors.nhs_number ? "has-error" : ""}`}>
          <label htmlFor="nhs-number">NHS number <span style={{ fontWeight: 'normal', color: 'var(--text-muted)' }}>(optional)</span></label>
          <input 
            id="nhs-number" 
            type="text" 
            inputMode="numeric" 
            placeholder="e.g. 485 777 3456" 
            style={{ width: '220px' }} 
            value={details.nhs_number ?? ""} 
            onChange={(e) => setField("nhs_number", formatNhsNumber(e.target.value))} 
          />
          {errors.nhs_number && <p className="error-message">{errors.nhs_number}</p>}
        </div>
      </div>

      {forSomeoneElse && (
        <div className="form-section">
          <h3>Your Details</h3>
          <div className={`field ${errors.submitter_name ? "has-error" : ""}`}>
            <label htmlFor="sub-name">Your name</label>
            <input id="sub-name" type="text" value={details.submitter_name ?? ""} onChange={(e) => setField("submitter_name", e.target.value)} />
            {errors.submitter_name && <p className="error-message">{errors.submitter_name}</p>}
          </div>
          <div className={`field ${errors.submitter_relationship ? "has-error" : ""}`}>
            <label htmlFor="sub-rel">Relationship to patient</label>
            <input id="sub-rel" type="text" placeholder="e.g. Parent" value={details.submitter_relationship ?? ""} onChange={(e) => setField("submitter_relationship", e.target.value)} />
            {errors.submitter_relationship && <p className="error-message">{errors.submitter_relationship}</p>}
          </div>
        </div>
      )}

      <div className="btn-row">
        <button className="btn btn-secondary" onClick={onBack}>Back</button>
        <button className="btn btn-primary" onClick={handleContinue}>Continue</button>
      </div>
    </PageShell>
  );
}
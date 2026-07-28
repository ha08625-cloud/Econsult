import { useState, useRef } from "react";
import { PageShell, FieldError } from "../layout";
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

// Human-readable labels for the error summary list
const ERROR_LABELS: Record<string, string> = {
  first_name: "First name",
  last_name: "Last name",
  dob: "Date of birth",
  postcode: "Postcode",
  gender: "Gender",
  nhs_number: "NHS number",
  submitter_name: "Your name",
  submitter_relationship: "Relationship to patient",
};

export default function PatientDetailsScreen({
  practiceName,
  onContinue,
  onBack,
}: PatientDetailsScreenProps) {
  const [details, setDetails] = useState<LocalPatientDetails>(initialiseDetails());
  const [errors, setErrors] = useState<Record<string, string>>({});

  // Ref for programmatic focus on the error summary after failed submission
  const summaryRef = useRef<HTMLDivElement>(null);

  const forSomeoneElse = details.patient_for === "someone_else";
  const hasErrors = Object.keys(errors).length > 0;

  function setField(key: keyof LocalPatientDetails, value: any) {
    setDetails((prev) => ({ ...prev, [key]: value }));
    if (errors[key] || (key.startsWith("dob") && errors.dob)) {
      setErrors((prev) => {
        const next = { ...prev };
        delete next[key];
        if (key.startsWith("dob")) delete next.dob;
        return next;
      });
    }
  }

  function handleDobChange(part: "day" | "month" | "year", value: string) {
    const cleanVal = value.replace(/\D/g, "").slice(0, part === "year" ? 4 : 2);

    const newDob = { ...details.date_of_birth, [part]: cleanVal };
    setField("date_of_birth", newDob);
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
      const isReal =
        assembled.getFullYear() === y &&
        assembled.getMonth() === m - 1 &&
        assembled.getDate() === d;

      if (!isReal) next.dob = "Enter a valid date.";
      else if (assembled > new Date()) next.dob = "Cannot be in the future.";
    }

    if (!details.postcode.trim()) next.postcode = "Enter a postcode.";
    else if (!UK_POSTCODE_REGEX.test(details.postcode.trim()))
      next.postcode = "Enter a valid UK postcode.";

    if (details.gender === null) next.gender = "Select a gender.";

    const nhsRaw = details.nhs_number ?? "";
    if (nhsRaw.trim() !== "" && !isValidNhsNumber(nhsRaw)) {
      next.nhs_number = "Enter a valid 10-digit NHS number.";
    }

    if (forSomeoneElse) {
      if (!details.submitter_name?.trim()) next.submitter_name = "Enter your name.";
      if (!details.submitter_relationship?.trim())
        next.submitter_relationship = "Enter relationship.";
    }

    if (Object.keys(next).length > 0) {
      setErrors(next);
      return false;
    }
    return true;
  }

  function handleContinue() {
    if (!validate()) {
      // Move focus to the error summary so screen readers announce it
      setTimeout(() => summaryRef.current?.focus(), 0);
      return;
    }
    const nhsStripped = (details.nhs_number ?? "").replace(/\s/g, "");
    const clean: PatientDetails = {
      ...details,
      first_name: details.first_name.trim(),
      last_name: details.last_name.trim(),
      gender: details.gender as Gender,
      nhs_number: nhsStripped || undefined,
      preferred_name: details.preferred_name?.trim() || undefined,
      submitter_name: forSomeoneElse ? details.submitter_name : undefined,
      submitter_relationship: forSomeoneElse
        ? details.submitter_relationship
        : undefined,
    } as PatientDetails;
    onContinue(clean);
  }

  return (
    <PageShell practiceName={practiceName}>
      <h1>About the patient</h1>
      <p className="screen-description">We need a few details before you continue.</p>

      {/* Error summary — rendered and focused on failed submission */}
      {hasErrors && (
        <div
          className="error-summary"
          role="alert"
          tabIndex={-1}
          ref={summaryRef}
        >
          <h2 className="error-summary-heading">There is a problem</h2>
          <ul className="error-summary-list">
            {Object.entries(errors).map(([key, message]) => (
              <li key={key}>
                {ERROR_LABELS[key] ? `${ERROR_LABELS[key]}: ` : ""}
                {message}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Form fields — wrapped for test scoping via within() */}
      <div data-testid="form-fields">

      {/* 1. Ownership Section */}
      <fieldset className={`field ${errors.patient_for ? "has-error" : ""}`}>
        <legend>Who is this consultation for?</legend>
        <div className="selection-grid">
          {(["me", "someone_else"] as const).map((val) => (
            <label
              key={val}
              className={`selection-card ${details.patient_for === val ? "selected" : ""}`}
            >
              <input
                type="radio"
                name="patient_for"
                checked={details.patient_for === val}
                onChange={() => setField("patient_for", val)}
              />
              <span className="selection-label">
                {val === "me" ? "Myself" : "Someone else"}
              </span>
            </label>
          ))}
        </div>
      </fieldset>

      {/* 2. Identity Section */}
      <div className="form-section">
        <div className={`field ${errors.first_name ? "has-error" : ""}`}>
          <label htmlFor="first-name">
            {forSomeoneElse ? "Patient's first name" : "First name"}
          </label>
          <input
            id="first-name"
            type="text"
            autoComplete={forSomeoneElse ? "off" : "given-name"}
            value={details.first_name}
            onChange={(e) => setField("first_name", e.target.value)}
            aria-invalid={!!errors.first_name}
            aria-describedby={errors.first_name ? "first-name-error" : undefined}
          />
          {errors.first_name && (
            <FieldError id="first-name-error" message={errors.first_name} />
          )}
        </div>

        <div className={`field ${errors.last_name ? "has-error" : ""}`}>
          <label htmlFor="last-name">
            {forSomeoneElse ? "Patient's last name" : "Last name"}
          </label>
          <input
            id="last-name"
            type="text"
            autoComplete={forSomeoneElse ? "off" : "family-name"}
            value={details.last_name}
            onChange={(e) => setField("last_name", e.target.value)}
            aria-invalid={!!errors.last_name}
            aria-describedby={errors.last_name ? "last-name-error" : undefined}
          />
          {errors.last_name && (
            <FieldError id="last-name-error" message={errors.last_name} />
          )}
        </div>

        <div className="field">
          <label htmlFor="preferred-name">
            Preferred name{" "}
            <span className="field-label-optional">(optional)</span>
          </label>
          <input
            id="preferred-name"
            type="text"
            value={details.preferred_name ?? ""}
            onChange={(e) => setField("preferred_name", e.target.value)}
          />
        </div>
      </div>

      {/* 3. Biological & Date Info */}
      <div className="form-section">
        <fieldset className={`field ${errors.gender ? "has-error" : ""}`}>
          <legend>{forSomeoneElse ? "Patient's gender" : "Gender"}</legend>
          <div className="selection-grid">
            {GENDER_OPTIONS.map(({ value, label }) => (
              <label
                key={value}
                className={`selection-card ${details.gender === value ? "selected" : ""}`}
              >
                <input
                  type="radio"
                  name="gender"
                  checked={details.gender === value}
                  onChange={() => setField("gender", value)}
                  aria-invalid={!!errors.gender}
                  aria-describedby={errors.gender ? "gender-error" : undefined}
                />
                <span className="selection-label">{label}</span>
              </label>
            ))}
          </div>
          {errors.gender && (
            <FieldError id="gender-error" message={errors.gender} />
          )}
        </fieldset>

        <fieldset className={`field ${errors.dob ? "has-error" : ""}`}>
          <legend>
            {forSomeoneElse ? "Patient's date of birth" : "Date of birth"}
          </legend>
          <div className="dob-inputs">
            <div className="dob-field">
              <label htmlFor="dob-day">Day</label>
              <input
                id="dob-day"
                type="text"
                inputMode="numeric"
                placeholder="DD"
                autoComplete={forSomeoneElse ? "off" : "bday-day"}
                className="input-dob-day-month"
                value={details.date_of_birth.day}
                onChange={(e) => handleDobChange("day", e.target.value)}
                aria-invalid={!!errors.dob}
                aria-describedby={errors.dob ? "dob-error" : undefined}
              />
            </div>
            <div className="dob-field">
              <label htmlFor="dob-month">Month</label>
              <input
                id="dob-month"
                type="text"
                inputMode="numeric"
                placeholder="MM"
                autoComplete={forSomeoneElse ? "off" : "bday-month"}
                className="input-dob-day-month"
                value={details.date_of_birth.month}
                onChange={(e) => handleDobChange("month", e.target.value)}
                aria-invalid={!!errors.dob}
                aria-describedby={errors.dob ? "dob-error" : undefined}
              />
            </div>
            <div className="dob-field">
              <label htmlFor="dob-year">Year</label>
              <input
                id="dob-year"
                type="text"
                inputMode="numeric"
                placeholder="YYYY"
                autoComplete={forSomeoneElse ? "off" : "bday-year"}
                className="input-dob-year"
                value={details.date_of_birth.year}
                onChange={(e) => handleDobChange("year", e.target.value)}
                aria-invalid={!!errors.dob}
                aria-describedby={errors.dob ? "dob-error" : undefined}
              />
            </div>
          </div>
          {errors.dob && <FieldError id="dob-error" message={errors.dob} />}
        </fieldset>
      </div>

      {/* 4. Administrative Info */}
      <div className="form-section">
        <div className={`field ${errors.postcode ? "has-error" : ""}`}>
          <label htmlFor="postcode">
            {forSomeoneElse ? "Patient's postcode" : "Postcode"}
          </label>
          <input
            id="postcode"
            type="text"
            autoComplete={forSomeoneElse ? "off" : "postal-code"}
            className="input-postcode"
            value={details.postcode}
            onChange={(e) => setField("postcode", e.target.value.toUpperCase())}
            aria-invalid={!!errors.postcode}
            aria-describedby={errors.postcode ? "postcode-error" : undefined}
          />
          {errors.postcode && (
            <FieldError id="postcode-error" message={errors.postcode} />
          )}
        </div>

        <div className={`field ${errors.nhs_number ? "has-error" : ""}`}>
          <label htmlFor="nhs-number">
            NHS number{" "}
            <span className="field-label-optional">(optional)</span>
          </label>
          <input
            id="nhs-number"
            type="text"
            inputMode="numeric"
            placeholder="e.g. 485 777 3456"
            className="input-nhs-number"
            value={details.nhs_number ?? ""}
            onChange={(e) =>
              setField("nhs_number", formatNhsNumber(e.target.value))
            }
            aria-invalid={!!errors.nhs_number}
            aria-describedby={errors.nhs_number ? "nhs-number-error" : undefined}
          />
          {errors.nhs_number && (
            <FieldError id="nhs-number-error" message={errors.nhs_number} />
          )}
        </div>
      </div>

      {forSomeoneElse && (
        <div className="form-section">
          <h3>Your details</h3>
          <div className={`field ${errors.submitter_name ? "has-error" : ""}`}>
            <label htmlFor="sub-name">Your name</label>
            <input
              id="sub-name"
              type="text"
              autoComplete="name"
              value={details.submitter_name ?? ""}
              onChange={(e) => setField("submitter_name", e.target.value)}
              aria-invalid={!!errors.submitter_name}
              aria-describedby={
                errors.submitter_name ? "submitter-name-error" : undefined
              }
            />
            {errors.submitter_name && (
              <FieldError
                id="submitter-name-error"
                message={errors.submitter_name}
              />
            )}
          </div>
          <div
            className={`field ${errors.submitter_relationship ? "has-error" : ""}`}
          >
            <label htmlFor="sub-rel">Relationship to patient</label>
            <input
              id="sub-rel"
              type="text"
              placeholder="e.g. Parent"
              value={details.submitter_relationship ?? ""}
              onChange={(e) =>
                setField("submitter_relationship", e.target.value)
              }
              aria-invalid={!!errors.submitter_relationship}
              aria-describedby={
                errors.submitter_relationship
                  ? "submitter-relationship-error"
                  : undefined
              }
            />
            {errors.submitter_relationship && (
              <FieldError
                id="submitter-relationship-error"
                message={errors.submitter_relationship}
              />
            )}
          </div>
        </div>
      )}

      </div>{/* end form-fields */}

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
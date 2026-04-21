import { useState, useRef } from "react";
import { PageShell, InlineError, FieldError } from "../layout";
import { finishForm, friendlyErrorMessage } from "../api";
import { initialiseContactPreferences, isValidUkPhone } from "../helpers";
import type { ContactPreferences, ContactMethod, PatientDetails, ConsultationOutcome } from "../types";

interface ContactScreenProps {
  practiceName: string | null;
  runtimeId: string;
  version: number;
  patientDetails: PatientDetails;
  consultationOutcome: ConsultationOutcome;
  photos: File[];
  /** Doctor names from GET /doctors. Empty array = no list configured; show free text only. */
  doctors: string[];
  onSubmit: () => void;
  onBack: () => void;
}

const ERROR_LABELS: Record<string, string> = {
  contact_methods: "Contact method",
  phone_number: "Phone number",
  email_address: "Email address",
  free_text_doctor: "Doctor preference",
  usual_doctor_name: "Doctor preference",
};

export default function ContactScreen({
  practiceName,
  runtimeId,
  version,
  patientDetails,
  consultationOutcome,
  photos,
  doctors,
  onSubmit,
  onBack,
}: ContactScreenProps) {
  const [contactPreferences, setContactPreferences] = useState<ContactPreferences>(
    initialiseContactPreferences()
  );
  const [contactErrors, setContactErrors] = useState<Record<string, string>>({});
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [screenError, setScreenError] = useState<string | null>(null);

  // Ref for programmatic focus on the error summary after failed submission
  const summaryRef = useRef<HTMLDivElement>(null);

  // When a list is shown, this tracks the value of the dropdown separately
  // from doctor_preference / usual_doctor_name so we can map to those fields
  // on submit. Values: "any" | "other" | <a doctor name from the list>.
  const [doctorSelection, setDoctorSelection] = useState<string>("any");
  // Free text box is always visible when a list is shown; also the sole
  // input when no list is configured.
  const [freeTextDoctor, setFreeTextDoctor] = useState<string>("");

  const cp = contactPreferences;
  const methods = cp.contact_methods;
  const wantsPhone = methods.includes("phone");
  const wantsText = methods.includes("text");
  const wantsPhoneOrText = wantsPhone || wantsText;
  const wantsEmail = methods.includes("email");
  const hasDoctorList = doctors.length > 0;
  const hasErrors = Object.keys(contactErrors).length > 0;

  function toggleMethod(method: ContactMethod) {
    const next = methods.includes(method)
      ? methods.filter((m) => m !== method)
      : [...methods, method];
    setContactPreferences({ ...cp, contact_methods: next });
    if (contactErrors.contact_methods) {
      setContactErrors((prev) => {
        const newErrors = { ...prev };
        delete newErrors.contact_methods;
        return newErrors;
      });
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

    // Doctor validation — list path
    if (hasDoctorList) {
      // "other" selected but free text box is empty: require a name.
      if (doctorSelection === "other" && !freeTextDoctor.trim()) {
        errors.free_text_doctor = "Please enter your doctor's name.";
      }
      // Named doctor selected or "any": no validation needed.
    } else {
      // Legacy path (no list): validate the existing field.
      if (cp.doctor_preference === "usual") {
        if (!cp.usual_doctor_name?.trim()) {
          errors.usual_doctor_name = "Please enter your doctor's name.";
        }
      }
    }

    if (Object.keys(errors).length > 0) {
      setContactErrors(errors);
      setTimeout(() => summaryRef.current?.focus(), 0);
      return;
    }

    // Build doctor preference fields for the payload.
    let doctorPreference: "any" | "usual";
    let usualDoctorName: string | null;

    if (hasDoctorList) {
      if (doctorSelection === "any") {
        doctorPreference = "any";
        usualDoctorName = null;
      } else if (doctorSelection === "other") {
        // Patient typed their own name.
        doctorPreference = "usual";
        usualDoctorName = freeTextDoctor.trim() || null;
      } else {
        // A named doctor was selected from the list — takes precedence over free text.
        doctorPreference = "usual";
        usualDoctorName = doctorSelection;
      }
    } else {
      // Legacy path.
      doctorPreference = cp.doctor_preference;
      usualDoctorName =
        cp.doctor_preference === "usual" ? (cp.usual_doctor_name?.trim() || null) : null;
    }

    // Build clean payload — null out fields that are not relevant.
    const cleanPreferences: ContactPreferences = {
      contact_methods: methods,
      email_address: wantsEmail ? (cp.email_address?.trim() || null) : null,
      phone_number: wantsPhoneOrText ? (cp.phone_number?.trim() || null) : null,
      best_time_to_call: wantsPhone ? (cp.best_time_to_call?.trim() || null) : null,
      doctor_preference: doctorPreference,
      usual_doctor_name: usualDoctorName,
      consultation_outcome: consultationOutcome,
    };

    setIsSubmitting(true);
    setScreenError(null);

    finishForm(runtimeId, version, cleanPreferences, patientDetails, photos)
      .then(() => {
        onSubmit();
      })
      .catch((e) => {
        setScreenError(friendlyErrorMessage(e));
      })
      .finally(() => {
        setIsSubmitting(false);
      });
  }

  return (
    <PageShell practiceName={practiceName}>
      <h1>How would you like to be contacted?</h1>

      <div className="alert alert-info" style={{ marginBottom: "var(--space-lg)" }}>
        <p>
          If you choose email or text message, we aim to respond within 2 working
          days. If you select phone call only, we aim to respond within 5 working
          days.
        </p>
      </div>

      {hasErrors && (
        <div
          className="error-summary"
          role="alert"
          tabIndex={-1}
          ref={summaryRef}
        >
          <h2 className="error-summary-heading">There is a problem</h2>
          <ul className="error-summary-list">
            {Object.entries(contactErrors).map(([key, message]) => (
              <li key={key}>
                {ERROR_LABELS[key] ? `${ERROR_LABELS[key]}: ` : ""}
                {message}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="form-section">
        <fieldset className={`field ${contactErrors.contact_methods ? "has-error" : ""}`}>
          <legend>Contact method (select all that apply)</legend>
          <div className="confirm-checkbox-row">
            {(["email", "text", "phone"] as ContactMethod[]).map((method) => {
              const labels: Record<ContactMethod, string> = {
                email: "Email",
                text: "Text message",
                phone: "Phone call",
              };
              return (
                <label key={method} className="confirm-checkbox-label">
                  <input
                    type="checkbox"
                    checked={methods.includes(method)}
                    onChange={() => toggleMethod(method)}
                    aria-invalid={!!contactErrors.contact_methods}
                    aria-describedby={
                      contactErrors.contact_methods ? "contact-methods-error" : undefined
                    }
                  />
                  <span>{labels[method]}</span>
                </label>
              );
            })}
          </div>
          {contactErrors.contact_methods && (
            <FieldError id="contact-methods-error" message={contactErrors.contact_methods} />
          )}
        </fieldset>

        {wantsPhoneOrText && (
          <div className={`field ${contactErrors.phone_number ? "has-error" : ""}`}>
            <label htmlFor="contact-phone">Phone number</label>
            <input
              id="contact-phone"
              type="tel"
              value={cp.phone_number ?? ""}
              onChange={(e) => {
                setContactPreferences({ ...cp, phone_number: e.target.value });
                if (contactErrors.phone_number) {
                  const newErrors = { ...contactErrors };
                  delete newErrors.phone_number;
                  setContactErrors(newErrors);
                }
              }}
              aria-invalid={!!contactErrors.phone_number}
              aria-describedby={contactErrors.phone_number ? "phone-error" : "phone-hint"}
            />
            <p id="phone-hint" className="field-hint">
              UK numbers only. We are unable to contact international numbers.
            </p>
            {contactErrors.phone_number && (
              <FieldError id="phone-error" message={contactErrors.phone_number} />
            )}
          </div>
        )}

        {wantsEmail && (
          <div className={`field ${contactErrors.email_address ? "has-error" : ""}`}>
            <label htmlFor="contact-email">Email address</label>
            <input
              id="contact-email"
              type="email"
              value={cp.email_address ?? ""}
              onChange={(e) => {
                setContactPreferences({ ...cp, email_address: e.target.value });
                if (contactErrors.email_address) {
                  const newErrors = { ...contactErrors };
                  delete newErrors.email_address;
                  setContactErrors(newErrors);
                }
              }}
              aria-invalid={!!contactErrors.email_address}
              aria-describedby={contactErrors.email_address ? "email-error" : undefined}
            />
            {contactErrors.email_address && (
              <FieldError id="email-error" message={contactErrors.email_address} />
            )}
          </div>
        )}

        {wantsPhone && (
          <div className="field">
            <label htmlFor="contact-best-time">Best time to call <span className="field-label-optional">(optional)</span></label>
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
      </div>

      <div className="form-section">
        {/* Doctor preference — list path */}
        {hasDoctorList ? (
          <>
            <div className="field">
              <label htmlFor="doctor-preference">Which doctor would you prefer to hear from?</label>
              <select
                id="doctor-preference"
                value={doctorSelection}
                onChange={(e) => {
                  setDoctorSelection(e.target.value);
                  if (contactErrors.free_text_doctor) {
                    const newErrors = { ...contactErrors };
                    delete newErrors.free_text_doctor;
                    setContactErrors(newErrors);
                  }
                }}
                className="combobox-input"
              >
                <option value="any">Soonest available doctor</option>
                <option value="other">Someone not on this list</option>
                {doctors.map((name) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
              </select>
            </div>

            <div className={`field ${contactErrors.free_text_doctor ? "has-error" : ""}`}>
              <label htmlFor="usual-doctor-name">
                If your preferred doctor is not listed above, please write their name here
              </label>
              <input
                id="usual-doctor-name"
                type="text"
                value={freeTextDoctor}
                onChange={(e) => {
                  setFreeTextDoctor(e.target.value);
                  if (contactErrors.free_text_doctor) {
                    const newErrors = { ...contactErrors };
                    delete newErrors.free_text_doctor;
                    setContactErrors(newErrors);
                  }
                }}
                aria-invalid={!!contactErrors.free_text_doctor}
                aria-describedby={contactErrors.free_text_doctor ? "free-text-doctor-error" : undefined}
              />
              {contactErrors.free_text_doctor && (
                <FieldError id="free-text-doctor-error" message={contactErrors.free_text_doctor} />
              )}
            </div>
          </>
        ) : (
          /* Doctor preference — legacy path (no list configured or fetch failed) */
          <>
            <div className="field">
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
                  const newErrors = { ...contactErrors };
                  delete newErrors.usual_doctor_name;
                  setContactErrors(newErrors);
                }
              }}
              className="combobox-input"
            >
              <option value="any">Soonest available doctor</option>
              <option value="usual">I would prefer my usual doctor</option>
            </select>
          </div>

          {cp.doctor_preference === "usual" && (
            <div className={`field ${contactErrors.usual_doctor_name ? "has-error" : ""}`}>
              <label htmlFor="usual-doctor-name">Please enter your doctor's name</label>
              <input
                id="usual-doctor-name"
                type="text"
                value={cp.usual_doctor_name ?? ""}
                onChange={(e) => {
                  setContactPreferences({ ...cp, usual_doctor_name: e.target.value });
                  if (contactErrors.usual_doctor_name) {
                    const newErrors = { ...contactErrors };
                    delete newErrors.usual_doctor_name;
                    setContactErrors(newErrors);
                  }
                }}
                aria-invalid={!!contactErrors.usual_doctor_name}
                aria-describedby={contactErrors.usual_doctor_name ? "usual-doctor-error" : undefined}
              />
              {contactErrors.usual_doctor_name && (
                <FieldError id="usual-doctor-error" message={contactErrors.usual_doctor_name} />
              )}
            </div>
          )}
        </>
      )}
      </div>

      {screenError && <InlineError message={screenError} />}

      <div className="btn-row">
        <button
          className="btn btn-secondary"
          disabled={isSubmitting}
          onClick={onBack}
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
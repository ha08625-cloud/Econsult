import { useState } from "react";
import { PageShell, InlineError } from "../layout";
import { finishForm, friendlyErrorMessage } from "../api";
import { initialiseContactPreferences, isValidUkPhone } from "../helpers";
import type { ContactPreferences, ContactMethod, PatientDetails } from "../types";

interface ContactScreenProps {
  practiceName: string | null;
  runtimeId: string;
  version: number;
  patientDetails: PatientDetails;
  onSubmit: () => void;
  onBack: () => void;
}

export default function ContactScreen({
  practiceName,
  runtimeId,
  version,
  patientDetails,
  onSubmit,
  onBack,
}: ContactScreenProps) {
  const [contactPreferences, setContactPreferences] = useState<ContactPreferences>(
    initialiseContactPreferences()
  );
  const [contactErrors, setContactErrors] = useState<Record<string, string>>({});
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [screenError, setScreenError] = useState<string | null>(null);

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

    finishForm(runtimeId, version, cleanPreferences, patientDetails)
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

"""
Delivery service.

Responsible for sending clinical output to the practice after a form submission.

This module defines:
  - DeliveryService: abstract base class
  - EmailDeliveryService: production SMTP implementation
  - ConsoleDeliveryService: local development only — logs to stdout, never sends email

Architecture rules:
  - This module must never access the database.
  - This module must never import clinical engine modules.
  - This module must never retry on failure.
  - This module must never update delivery status (that is the router's responsibility).
  - contact_preferences and patient_details are carried inside ClinicalOutput;
    the interface does not need separate parameters.

Configuration (EmailDeliveryService):
    SMTP_HOST, SMTP_PORT (default 587), SMTP_USER, SMTP_PASSWORD,
    EMAIL_FROM, SMTP_TIMEOUT (default 30)

ConsoleDeliveryService is for local development only. Never instantiate in production.
"""

import logging
import os
import smtplib
from abc import ABC, abstractmethod
from datetime import date, datetime
from email.message import EmailMessage

from app.models.serialisation_contracts import ClinicalOutput, PatientDetails

logger = logging.getLogger(__name__)


class EmailDeliveryError(Exception):
    pass


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class DeliveryService(ABC):
    @abstractmethod
    def send_clinical_output(
        self,
        to_email: str,
        condition_label: str,
        clinical_output: ClinicalOutput,
        submission_id: str,
    ) -> None: ...


# ---------------------------------------------------------------------------
# Formatting helpers (internal to this module — email format details)
# ---------------------------------------------------------------------------

def _format_answer(value) -> str:
    if value is True:
        return "Yes"
    if value is False:
        return "No"
    if value is None:
        return "(not answered)"
    return str(value)


def _format_patient_details(pd: PatientDetails) -> list[str]:
    """
    Return lines for the patient details section.

    date_of_birth is stored as ISO 8601 ("1990-03-15") and formatted here
    as "15 March 1990" for human readability in the email body.

    Note: strftime("%-d %B %Y") uses a Linux-specific directive (%-d) to
    suppress the leading zero on the day. This is intentional — the system
    deploys on Linux (Railway). It will raise ValueError on Windows.
    """
    dob_formatted = date.fromisoformat(pd.date_of_birth).strftime("%-d %B %Y")
    patient_line = (
        f"Patient: {pd.first_name} {pd.last_name}, "
        f"DOB {dob_formatted}, "
        f"Postcode {pd.postcode.upper()}"
    )
    lines = [patient_line]

    if pd.patient_for == "someone_else" and pd.submitter_name:
        relationship = f" ({pd.submitter_relationship})" if pd.submitter_relationship else ""
        lines.append(f"Submitted by: {pd.submitter_name}{relationship}")

    return lines


def _format_contact_preferences(cp: dict) -> list[str]:
    """
    Return lines for the contact preferences section.
    Omits any field that is null or empty rather than printing 'None'.
    """
    lines = [
        "",
        "CONTACT PREFERENCES",
        "-" * 40,
    ]

    methods = cp.get("contact_methods") or []
    method_labels = {"email": "Email", "text": "Text message", "phone": "Phone call"}
    readable_methods = ", ".join(method_labels.get(m, m) for m in methods)
    if readable_methods:
        lines.append(f"  Contact methods: {readable_methods}")

    email_address = cp.get("email_address")
    if email_address:
        lines.append(f"  Email address: {email_address}")

    phone_number = cp.get("phone_number")
    if phone_number:
        lines.append(f"  Phone number: {phone_number}")

    best_time = cp.get("best_time_to_call")
    if best_time:
        lines.append(f"  Best time to call: {best_time}")

    doctor_pref = cp.get("doctor_preference")
    if doctor_pref == "usual":
        lines.append("  Doctor preference: Usual doctor")
        usual_name = cp.get("usual_doctor_name")
        if usual_name:
            lines.append(f"  Usual doctor name: {usual_name}")
    elif doctor_pref == "any":
        lines.append("  Doctor preference: Soonest available doctor")

    return lines


def _format_body(
    condition_label: str,
    clinical_output: ClinicalOutput,
    submission_id: str,
) -> str:
    lines = [
        "E-CONSULTATION SUBMISSION",
        "=" * 40,
        "",
        f"Condition:     {condition_label}",
        f"Submission ID: {submission_id}",
        f"Submitted at:  {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC",
        "",
    ]

    # Patient details block — inserted before clinical content
    lines += _format_patient_details(clinical_output.patient_details)

    lines += [
        "",
        "PATIENT DESCRIPTION",
        "-" * 40,
        clinical_output.free_text or "(none provided)",
        "",
        "ANSWERS",
        "-" * 40,
    ]

    for key, value in clinical_output.answers.items():
        label = clinical_output.question_labels.get(key, key)
        lines.append(f"  {label}: {_format_answer(value)}")

    if clinical_output.additional_text:
        lines += [
            "",
            "ADDITIONAL INFORMATION",
            "-" * 40,
            clinical_output.additional_text,
        ]

    if clinical_output.safety_messages:
        lines += [
            "",
            "SAFETY FLAGS",
            "-" * 40,
        ]
        for msg in clinical_output.safety_messages:
            lines.append(f"  [{msg.get('id', '')}] {msg.get('text', '')}")

    if clinical_output.contact_preferences:
        lines += _format_contact_preferences(clinical_output.contact_preferences)

    lines += [
        "",
        "=" * 40,
        "This message was generated automatically by the e-consultation system.",
        "Do not reply to this email.",
    ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Production implementation
# ---------------------------------------------------------------------------

class EmailDeliveryService(DeliveryService):
    """
    Sends clinical output via SMTP.

    SMTP configuration is read from environment variables at instantiation time.
    A missing variable will raise RuntimeError at startup, not silently at send time.
    """

    def __init__(self) -> None:
        self._smtp_host = self._require_env("SMTP_HOST")
        self._smtp_port = int(os.environ.get("SMTP_PORT", "587"))
        self._smtp_user = self._require_env("SMTP_USER")
        self._smtp_password = self._require_env("SMTP_PASSWORD")
        self._email_from = self._require_env("EMAIL_FROM")
        self._smtp_timeout = int(os.environ.get("SMTP_TIMEOUT", "30"))

    @staticmethod
    def _require_env(name: str) -> str:
        value = os.environ.get(name)
        if not value:
            raise RuntimeError(
                f"EmailDeliveryService requires environment variable: {name}"
            )
        return value

    def send_clinical_output(
        self,
        to_email: str,
        condition_label: str,
        clinical_output: ClinicalOutput,
        submission_id: str,
    ) -> None:
        subject = f"E-consultation: {condition_label} [{submission_id}]"
        body = _format_body(condition_label, clinical_output, submission_id)

        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = self._email_from
        msg["To"] = to_email
        msg.set_content(body)

        try:
            with smtplib.SMTP(self._smtp_host, self._smtp_port, timeout=self._smtp_timeout) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(self._smtp_user, self._smtp_password)
                server.send_message(msg)
        except Exception as e:
            raise EmailDeliveryError(str(e)) from e


# ---------------------------------------------------------------------------
# Development implementation
# ConsoleDeliveryService is for local development only. Never instantiate in production.
# ---------------------------------------------------------------------------

class ConsoleDeliveryService(DeliveryService):
    """
    Logs clinical output to stdout instead of sending email.

    For local development only. Raises RuntimeError if DEV_MODE is not set,
    to prevent accidental use in production.
    """

    def __init__(self) -> None:
        if os.environ.get("DEV_MODE", "").lower() not in ("1", "true"):
            raise RuntimeError(
                "ConsoleDeliveryService may only be instantiated when DEV_MODE=1. "
                "Use EmailDeliveryService in production."
            )

    def send_clinical_output(
        self,
        to_email: str,
        condition_label: str,
        clinical_output: ClinicalOutput,
        submission_id: str,
    ) -> None:
        body = _format_body(condition_label, clinical_output, submission_id)
        logger.info(
            "[DEV_MODE] Email send skipped. Would have sent:\n"
            "  To:      %s\n"
            "  Subject: E-consultation: %s [%s]\n"
            "  Body:\n%s",
            to_email,
            condition_label,
            submission_id,
            "\n".join(f"    {line}" for line in body.splitlines()),
        )
"""
Email service.

Responsible for sending clinical output to the practice email address
after a form submission.

This module is responsible for:
- Formatting the clinical output as a plain text email body
- Sending via SMTP in production mode
- Logging to stdout in DEV_MODE without sending

Configuration via environment variables:
    SMTP_HOST       - required in production
    SMTP_PORT       - optional, default 587
    SMTP_USER       - required in production
    SMTP_PASSWORD   - required in production
    EMAIL_FROM      - required in production
    SMTP_TIMEOUT    - optional, default 30 seconds
    DEV_MODE        - if set to '1' or 'true', skips SMTP and logs to stdout

This module must never:
- Access the database
- Import clinical engine modules (form_logic, safety_engine, etc.)
- Retry on failure (retry logic belongs in the calling layer)
- Update delivery status (that belongs in submission_repository)
"""

import os
import smtplib
from email.message import EmailMessage
from datetime import datetime

from contracts.serialisation_contracts import ClinicalOutput


class EmailDeliveryError(Exception):
    """
    Raised when email sending fails for any reason.
    The string representation contains the underlying error message,
    suitable for storing in submission_records.delivery_error.
    """
    pass


def _is_dev_mode() -> bool:
    return os.environ.get("DEV_MODE", "").lower() in ("1", "true")


def _format_answer(value) -> str:
    """Format a single answer value for display in the email body."""
    if value is True:
        return "Yes"
    if value is False:
        return "No"
    if value is None:
        return "(not answered)"
    return str(value)


def _format_body(
    condition_label: str,
    clinical_output: ClinicalOutput,
    submission_id: str,
) -> str:
    """
    Format a plain text email body from clinical output.

    answer_keys are used directly as field labels. Question text is not
    available to this module — if human-readable labels are needed in future,
    they should be added to ClinicalOutput, not loaded here from the ruleset.
    """
    lines = [
        "E-CONSULTATION SUBMISSION",
        "=" * 40,
        "",
        f"Condition:     {condition_label}",
        f"Submission ID: {submission_id}",
        f"Submitted at:  {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC",
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

    if clinical_output.safety_messages:
        lines.append("")
        lines.append("SAFETY FLAGS")
        lines.append("-" * 40)
        for msg in clinical_output.safety_messages:
            lines.append(f"  [{msg.get('id', '')}] {msg.get('text', '')}")

    lines += [
        "",
        "=" * 40,
        "This message was generated automatically by the e-consultation system.",
        "Do not reply to this email.",
    ]

    return "\n".join(lines)


def send_clinical_output(
    to_email: str,
    condition_label: str,
    clinical_output: ClinicalOutput,
    submission_id: str,
) -> None:
    """
    Send clinical output to the practice email address.

    In DEV_MODE: logs the full email content to stdout. Does not connect
    to any SMTP server. Does not raise EmailDeliveryError.

    In production mode: sends via SMTP using environment variable configuration.
    Raises EmailDeliveryError on any failure, including connection errors,
    authentication failures, and timeouts.

    This function does not update the submission record. The caller is
    responsible for updating delivery_status based on success or failure.
    """
    subject = f"E-consultation: {condition_label} [{submission_id}]"
    body = _format_body(condition_label, clinical_output, submission_id)

    if _is_dev_mode():
        print("[DEV_MODE] Email send skipped. Would have sent:")
        print(f"  To:      {to_email}")
        print(f"  Subject: {subject}")
        print("  Body:")
        for line in body.splitlines():
            print(f"    {line}")
        return

    smtp_host = os.environ["SMTP_HOST"]
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ["SMTP_USER"]
    smtp_password = os.environ["SMTP_PASSWORD"]
    email_from = os.environ["EMAIL_FROM"]
    smtp_timeout = int(os.environ.get("SMTP_TIMEOUT", "30"))

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = email_from
    msg["To"] = to_email
    msg.set_content(body)

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=smtp_timeout) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(smtp_user, smtp_password)
            server.send_message(msg)
    except Exception as e:
        raise EmailDeliveryError(str(e)) from e
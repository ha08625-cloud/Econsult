"""
app/services/delivery/admin_delivery_service.py

Transport layer for admin MFA emails.

Responsibilities:
- Send a single plain-text MFA code email over SMTP.

Strict boundaries:
- This service has no knowledge of admin_auth_codes, AuthRepository,
  or any cooldown/rate-limit logic.
- The decision of whether to send is made entirely by auth_service.py.
  This service is called only after that decision has been made.
- Uses the same SMTP environment variables as EmailDeliveryService but
  opens a completely separate SMTP connection on every call. No shared
  state or connection pool with the clinical delivery path.

SMTP configuration is read from environment variables at instantiation
time. A missing variable raises RuntimeError at startup rather than
silently failing at send time. This matches the pattern used by
EmailDeliveryService.
"""

import logging
import os
import smtplib
from email.message import EmailMessage

logger = logging.getLogger(__name__)


class AdminDeliveryService:

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
                f"AdminDeliveryService requires environment variable: {name}"
            )
        return value

    def send_mfa_code(self, email: str, code: str) -> None:
        """
        Send a plain-text MFA code email to the given address.

        Email body is a hardcoded plain-text string — no HTML, no headers,
        no attachments, no clinical branding.

        Raises smtplib.SMTPException (or subclass) if the SMTP connection
        or send fails. The caller (auth_service.request_mfa_code) should
        let this propagate — a failed send is a genuine error.
        """
        body = (
            f"Your Econsult admin security code is: {code}. "
            "It expires in 10 minutes."
        )

        msg = EmailMessage()
        msg["Subject"] = "Your Econsult admin security code"
        msg["From"] = self._email_from
        msg["To"] = email
        msg.set_content(body)

        with smtplib.SMTP(self._smtp_host, self._smtp_port, timeout=self._smtp_timeout) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(self._smtp_user, self._smtp_password)
            server.send_message(msg)

        logger.info("MFA code sent to %s", email)


class ConsoleAdminDeliveryService:
    """
    Logs the MFA code to stdout instead of sending email.

    For local development only. Raises RuntimeError at instantiation if
    DEV_MODE is not set, to prevent accidental use in production.
    """

    def __init__(self) -> None:
        if os.environ.get("DEV_MODE", "").lower() not in ("1", "true"):
            raise RuntimeError(
                "ConsoleAdminDeliveryService may only be instantiated when "
                "DEV_MODE=1. Use AdminDeliveryService in production."
            )

    def send_mfa_code(self, email: str, code: str) -> None:
        logger.info(
            "[DEV_MODE] MFA email send skipped. Would have sent to %s: code=%s",
            email,
            code,
        )
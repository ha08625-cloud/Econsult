"""
app/services/delivery/admin_delivery_service.py

Transport layer for admin emails.

Responsibilities:
- Send a single plain-text MFA code email.
- Send a plain-text admin invitation email.

This module defines:
  - AdminDeliveryService: production SMTP implementation
  - MailgunHttpAdminDeliveryService: production Mailgun HTTP API implementation
  - ConsoleAdminDeliveryService: local development only — logs to stdout, never sends email

Strict boundaries:
- This service has no knowledge of admin_auth_codes, AuthRepository,
  or any cooldown/rate-limit logic.
- The decision of whether to send is made entirely by auth_service.py or
  the admin user router. This service is called only after that decision
  has been made.

Service selection (main.py):
    If MAILGUN_API_KEY is set, MailgunHttpAdminDeliveryService is used.
    Otherwise AdminDeliveryService (SMTP) is used.

SMTP configuration is read from environment variables at instantiation
time. A missing variable raises RuntimeError at startup rather than
silently failing at send time.

ADMIN_PORTAL_URL:
    Optional. Used in invitation emails to tell the new admin where to go.
    Defaults to "the admin portal" if not set. Read at call time (not
    instantiation) so it can be set after the service is created in tests.
"""

import logging
import os
import smtplib
from email.message import EmailMessage

import requests

logger = logging.getLogger(__name__)

_MAILGUN_EU_API_BASE = "https://api.eu.mailgun.net/v3"


def _admin_portal_url() -> str:
    """Return the admin portal URL from the environment, or a plain fallback."""
    return os.environ.get("ADMIN_PORTAL_URL", "the admin portal")


# ---------------------------------------------------------------------------
# SMTP implementation
# ---------------------------------------------------------------------------

class AdminDeliveryService:
    """
    Sends admin emails via SMTP.

    Uses the same SMTP environment variables as EmailDeliveryService but
    opens a completely separate SMTP connection on every call. No shared
    state or connection pool with the clinical delivery path.
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
                f"AdminDeliveryService requires environment variable: {name}"
            )
        return value

    def _send(self, to: str, subject: str, body: str) -> None:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = self._email_from
        msg["To"] = to
        msg.set_content(body)

        with smtplib.SMTP(self._smtp_host, self._smtp_port, timeout=self._smtp_timeout) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(self._smtp_user, self._smtp_password)
            server.send_message(msg)

    def send_mfa_code(self, email: str, code: str) -> None:
        """
        Send a plain-text MFA code email to the given address.

        Raises smtplib.SMTPException (or subclass) if the SMTP connection
        or send fails. The caller (auth_service.request_mfa_code) should
        let this propagate — a failed send is a genuine error.
        """
        body = (
            f"Your Econsult admin security code is: {code}. "
            "It expires in 10 minutes."
        )
        self._send(email, "Your Econsult admin security code", body)
        logger.info("MFA code sent to %s", email)

    def send_admin_invitation(self, email: str) -> None:
        """
        Send a plain-text invitation email to a newly added admin.

        Raises smtplib.SMTPException (or subclass) if the send fails.
        The caller (admin_user_router) catches this and returns
        email_sent: false rather than propagating the error.
        """
        url = _admin_portal_url()
        body = (
            f"You have been added as an admin. "
            f"Go to {url} and log in using this email address to receive an MFA code."
        )
        self._send(email, "You have been added as an Econsult admin", body)
        logger.info("Admin invitation sent to %s", email)


# ---------------------------------------------------------------------------
# Mailgun HTTP API implementation
# ---------------------------------------------------------------------------

class MailgunHttpAdminDeliveryService:
    """
    Sends admin emails via the Mailgun HTTP API.

    Uses the EU regional endpoint. Configuration is read from environment
    variables at instantiation time. A missing variable raises RuntimeError
    at startup, not silently at send time.

    This implementation exists because Railway's free and hobby plans block
    outbound SMTP connections. The HTTP API is the recommended alternative.
    """

    def __init__(self) -> None:
        self._api_key = self._require_env("MAILGUN_API_KEY")
        self._domain = self._require_env("MAILGUN_DOMAIN")
        self._email_from = self._require_env("EMAIL_FROM")

    @staticmethod
    def _require_env(name: str) -> str:
        value = os.environ.get(name)
        if not value:
            raise RuntimeError(
                f"MailgunHttpAdminDeliveryService requires environment variable: {name}"
            )
        return value

    def _send(self, to: str, subject: str, body: str) -> None:
        url = f"{_MAILGUN_EU_API_BASE}/{self._domain}/messages"
        response = requests.post(
            url,
            auth=("api", self._api_key),
            data={
                "from": self._email_from,
                "to": to,
                "subject": subject,
                "text": body,
            },
            timeout=30,
        )
        response.raise_for_status()

    def send_mfa_code(self, email: str, code: str) -> None:
        """
        Send a plain-text MFA code email via the Mailgun HTTP API.

        Raises requests.RequestException if the HTTP call fails.
        The caller (auth_service.request_mfa_code) should let this
        propagate — a failed send is a genuine error.
        """
        body = (
            f"Your Econsult admin security code is: {code}. "
            "It expires in 10 minutes."
        )
        self._send(email, "Your Econsult admin security code", body)
        logger.info("MFA code sent to %s", email)

    def send_admin_invitation(self, email: str) -> None:
        """
        Send a plain-text invitation email to a newly added admin.

        Raises requests.RequestException if the HTTP call fails.
        The caller (admin_user_router) catches this and returns
        email_sent: false rather than propagating the error.
        """
        url = _admin_portal_url()
        body = (
            f"You have been added as an admin. "
            f"Go to {url} and log in using this email address to receive an MFA code."
        )
        self._send(email, "You have been added as an Econsult admin", body)
        logger.info("Admin invitation sent to %s", email)


# ---------------------------------------------------------------------------
# Development implementation
# ConsoleAdminDeliveryService is for local development only. Never instantiate in production.
# ---------------------------------------------------------------------------

class ConsoleAdminDeliveryService:
    """
    Logs admin emails to stdout instead of sending them.

    For local development only. Raises RuntimeError at instantiation if
    DEV_MODE is not set, to prevent accidental use in production.
    """

    def __init__(self) -> None:
        if os.environ.get("DEV_MODE", "").lower() not in ("1", "true"):
            raise RuntimeError(
                "ConsoleAdminDeliveryService may only be instantiated when "
                "DEV_MODE=1. Use MailgunHttpAdminDeliveryService or "
                "AdminDeliveryService in production."
            )

    def send_mfa_code(self, email: str, code: str) -> None:
        logger.info(
            "[DEV_MODE] MFA email send skipped. Would have sent to %s: code=%s",
            email,
            code,
        )

    def send_admin_invitation(self, email: str) -> None:
        logger.info(
            "[DEV_MODE] Invitation email send skipped. Would have sent to %s",
            email,
        )
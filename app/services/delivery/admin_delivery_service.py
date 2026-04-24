"""
app/services/delivery/admin_delivery_service.py

Transport layer for admin emails.

Responsibilities:
- Send a plain-text MFA code email (send_mfa_code).
- Send a plain-text admin setup/invitation email (send_admin_invitation).

This module defines:
  - AdminDeliveryService: production SMTP implementation
  - MailgunHttpAdminDeliveryService: production Mailgun HTTP API implementation
  - ConsoleAdminDeliveryService: local development only — logs to stdout, never sends email

Strict boundaries:
- This service has no knowledge of admin_auth_codes, AuthRepository,
  or any cooldown/rate-limit logic.
- The decision of whether to send is made entirely by the caller.
  This service is called only after that decision has been made.

Service selection (main.py):
    If MAILGUN_API_KEY is set, MailgunHttpAdminDeliveryService is used.
    Otherwise AdminDeliveryService (SMTP) is used.

Configuration is read from environment variables at instantiation time.
A missing variable raises RuntimeError at startup rather than silently
failing at send time.

Required environment variables (all implementations):
    ADMIN_URL   — full URL of the admin portal, used to construct the
                  password setup link in invitation emails
                  (e.g. https://my-practice.up.railway.app/admin)

ConsoleAdminDeliveryService reads ADMIN_URL but does not require it —
defaults to http://localhost/admin if absent, since emails are never sent
in DEV_MODE.
"""

import logging
import os
import smtplib
from email.message import EmailMessage

import requests

logger = logging.getLogger(__name__)

_MAILGUN_EU_API_BASE = "https://api.eu.mailgun.net/v3"


# ---------------------------------------------------------------------------
# SMTP implementation
# ---------------------------------------------------------------------------

class AdminDeliveryService:
    """
    Sends admin MFA codes and setup invitations via SMTP.

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
        self._admin_url = self._require_env("ADMIN_URL")

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
        or send fails. The caller should let this propagate — a failed send
        is a genuine error.
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

    def send_admin_invitation(self, email: str, token: str) -> None:
        """
        Send a plain-text setup/invitation email to an admin user.

        The token is embedded in the URL hash as #reset:{token}. The hash
        fragment is never sent to the server, so the raw token is not logged
        in server access logs. The admin portal's App.tsx detects the hash
        on load and routes to SetPasswordView.

        Raises smtplib.SMTPException (or subclass) if the SMTP connection
        or send fails. The caller (admin_user_router) should catch this and
        return email_sent: false rather than raising a 500.
        """
        setup_url = f"{self._admin_url}#reset:{token}"
        body = (
            "You have been added as an administrator for this practice. "
            f"Set up your password at: {setup_url}\n\n"
            "This link expires in 1 hour. If you did not expect this email, "
            "you can ignore it."
        )

        msg = EmailMessage()
        msg["Subject"] = "Set up your Econsult admin account"
        msg["From"] = self._email_from
        msg["To"] = email
        msg.set_content(body)

        with smtplib.SMTP(self._smtp_host, self._smtp_port, timeout=self._smtp_timeout) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(self._smtp_user, self._smtp_password)
            server.send_message(msg)

        logger.info("Invitation email sent to %s", email)


# ---------------------------------------------------------------------------
# Mailgun HTTP API implementation
# ---------------------------------------------------------------------------

class MailgunHttpAdminDeliveryService:
    """
    Sends admin MFA codes and setup invitations via the Mailgun HTTP API.

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
        self._admin_url = self._require_env("ADMIN_URL")

    @staticmethod
    def _require_env(name: str) -> str:
        value = os.environ.get(name)
        if not value:
            raise RuntimeError(
                f"MailgunHttpAdminDeliveryService requires environment variable: {name}"
            )
        return value

    def send_mfa_code(self, email: str, code: str) -> None:
        """
        Send a plain-text MFA code email via the Mailgun HTTP API.

        Raises requests.RequestException if the HTTP call fails.
        The caller should let this propagate — a failed send is a genuine error.
        """
        body = (
            f"Your Econsult admin security code is: {code}. "
            "It expires in 10 minutes."
        )

        url = f"{_MAILGUN_EU_API_BASE}/{self._domain}/messages"

        response = requests.post(
            url,
            auth=("api", self._api_key),
            data={
                "from": self._email_from,
                "to": email,
                "subject": "Your Econsult admin security code",
                "text": body,
            },
            timeout=30,
        )
        response.raise_for_status()

        logger.info("MFA code sent to %s", email)

    def send_admin_invitation(self, email: str, token: str) -> None:
        """
        Send a plain-text setup/invitation email via the Mailgun HTTP API.

        The token is embedded in the URL hash as #reset:{token}. The hash
        fragment is never sent to the server, so the raw token is not logged
        in server access logs.

        Raises requests.RequestException if the HTTP call fails.
        The caller (admin_user_router) should catch this and return
        email_sent: false rather than raising a 500.
        """
        setup_url = f"{self._admin_url}#reset:{token}"
        body = (
            "You have been added as an administrator for this practice. "
            f"Set up your password at: {setup_url}\n\n"
            "This link expires in 1 hour. If you did not expect this email, "
            "you can ignore it."
        )

        url = f"{_MAILGUN_EU_API_BASE}/{self._domain}/messages"

        response = requests.post(
            url,
            auth=("api", self._api_key),
            data={
                "from": self._email_from,
                "to": email,
                "subject": "Set up your Econsult admin account",
                "text": body,
            },
            timeout=30,
        )
        response.raise_for_status()

        logger.info("Invitation email sent to %s", email)


# ---------------------------------------------------------------------------
# Development implementation
# ConsoleAdminDeliveryService is for local development only. Never instantiate in production.
# ---------------------------------------------------------------------------

class ConsoleAdminDeliveryService:
    """
    Logs the MFA code and invitation URL to stdout instead of sending email.

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
        self._admin_url = os.environ.get("ADMIN_URL", "http://localhost/admin")

    def send_mfa_code(self, email: str, code: str) -> None:
        logger.info(
            "[DEV_MODE] MFA email send skipped. Would have sent to %s: code=%s",
            email,
            code,
        )

    def send_admin_invitation(self, email: str, token: str) -> None:
        setup_url = f"{self._admin_url}#reset:{token}"
        logger.info(
            "[DEV_MODE] Invitation email send skipped. Would have sent to %s: url=%s",
            email,
            setup_url,
        )
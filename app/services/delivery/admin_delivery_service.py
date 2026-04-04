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
  as a completely separate SMTP connection. No shared state with the
  clinical delivery path.
"""


class AdminDeliveryService:

    def send_mfa_code(self, email: str, code: str) -> None:
        """
        Send a plain-text MFA code email to the given address.

        The email body is a hardcoded plain-text string:
          "Your Econsult admin security code is: {code}.
           It expires in 10 minutes."

        No HTML, no headers, no attachments, no clinical branding.

        Raises an exception if the SMTP connection or send fails.
        The caller (auth_service.request_mfa_code) should let this
        propagate — a failed send is a genuine error, not a silent no-op.
        """
        raise NotImplementedError
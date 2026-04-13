"""
Unit tests for delivery_service.py.

Tests the static email body format, ConsoleDeliveryService behaviour,
and MailgunHttpDeliveryService behaviour.
No database or SMTP connection required.
"""

import os
import logging
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

import pytest

from app.services.delivery.delivery_service import (
    ConsoleDeliveryService,
    EmailDeliveryError,
    MailgunHttpDeliveryService,
    _format_body,
)


# ---------------------------------------------------------------------------
# _format_body
# ---------------------------------------------------------------------------

class TestFormatBody:
    def test_contains_submission_id(self):
        body = _format_body(
            condition_label="Earache",
            submission_id="abc12345-0000-0000-0000-000000000000",
            submitted_at=datetime(2026, 3, 25, 10, 30, 0, tzinfo=timezone.utc),
        )
        assert "abc12345-0000-0000-0000-000000000000" in body

    def test_contains_condition_label(self):
        body = _format_body(
            condition_label="Earache",
            submission_id="abc12345",
            submitted_at=datetime(2026, 3, 25, 10, 30, 0, tzinfo=timezone.utc),
        )
        assert "Earache" in body

    def test_contains_submitted_at_formatted(self):
        body = _format_body(
            condition_label="Earache",
            submission_id="abc12345",
            submitted_at=datetime(2026, 3, 25, 10, 30, 0, tzinfo=timezone.utc),
        )
        assert "2026-03-25 10:30:00" in body
        assert "UTC" in body

    def test_contains_pdf_instruction(self):
        body = _format_body(
            condition_label="Earache",
            submission_id="abc12345",
            submitted_at=datetime(2026, 3, 25, 10, 30, 0, tzinfo=timezone.utc),
        )
        assert "attached PDF" in body

    def test_contains_do_not_reply(self):
        body = _format_body(
            condition_label="Earache",
            submission_id="abc12345",
            submitted_at=datetime(2026, 3, 25, 10, 30, 0, tzinfo=timezone.utc),
        )
        assert "Do not reply" in body

    def test_does_not_contain_patient_details(self):
        """The static body must never contain clinical or patient information."""
        body = _format_body(
            condition_label="Earache",
            submission_id="abc12345",
            submitted_at=datetime(2026, 3, 25, 10, 30, 0, tzinfo=timezone.utc),
        )
        assert "PATIENT DETAILS" not in body
        assert "PATIENT DESCRIPTION" not in body
        assert "ANSWERS" not in body
        assert "CONTACT PREFERENCES" not in body
        assert "SAFETY FLAGS" not in body


# ---------------------------------------------------------------------------
# ConsoleDeliveryService
# ---------------------------------------------------------------------------

class TestConsoleDeliveryService:
    def test_send_does_not_raise(self):
        with patch.dict(os.environ, {"DEV_MODE": "1"}):
            svc = ConsoleDeliveryService()
            svc.send_clinical_output(
                to_email="gp@example.com",
                condition_label="Earache",
                pdf_bytes=b"%PDF-fake-content",
                submission_id="abc12345-0000-0000-0000-000000000000",
                submitted_at=datetime(2026, 3, 25, 10, 30, 0, tzinfo=timezone.utc),
            )

    def test_send_logs_expected_fields(self, caplog):
        with patch.dict(os.environ, {"DEV_MODE": "1"}):
            svc = ConsoleDeliveryService()
            with caplog.at_level(logging.INFO):
                svc.send_clinical_output(
                    to_email="gp@example.com",
                    condition_label="Earache",
                    pdf_bytes=b"%PDF-fake-content",
                    submission_id="abc12345-0000-0000-0000-000000000000",
                    submitted_at=datetime(2026, 3, 25, 10, 30, 0, tzinfo=timezone.utc),
                )
        log_text = caplog.text
        assert "gp@example.com" in log_text
        assert "Earache" in log_text
        assert "abc12345" in log_text
        assert "17 bytes" in log_text  # len(b"%PDF-fake-content")

    def test_raises_without_dev_mode(self):
        with patch.dict(os.environ, {"DEV_MODE": ""}, clear=False):
            with pytest.raises(RuntimeError, match="DEV_MODE"):
                ConsoleDeliveryService()


# ---------------------------------------------------------------------------
# MailgunHttpDeliveryService
# ---------------------------------------------------------------------------

_MAILGUN_ENV = {
    "MAILGUN_API_KEY": "key-test123",
    "MAILGUN_DOMAIN": "mail.summertownhealthcentrechat.co.uk",
    "EMAIL_FROM": "noreply@mail.summertownhealthcentrechat.co.uk",
}


class TestMailgunHttpDeliveryService:
    def test_raises_without_api_key(self):
        env = {**_MAILGUN_ENV}
        del env["MAILGUN_API_KEY"]
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(RuntimeError, match="MAILGUN_API_KEY"):
                MailgunHttpDeliveryService()

    def test_raises_without_domain(self):
        env = {**_MAILGUN_ENV}
        del env["MAILGUN_DOMAIN"]
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(RuntimeError, match="MAILGUN_DOMAIN"):
                MailgunHttpDeliveryService()

    def test_raises_without_email_from(self):
        env = {**_MAILGUN_ENV}
        del env["EMAIL_FROM"]
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(RuntimeError, match="EMAIL_FROM"):
                MailgunHttpDeliveryService()

    def test_send_calls_correct_eu_endpoint(self):
        with patch.dict(os.environ, _MAILGUN_ENV, clear=True):
            svc = MailgunHttpDeliveryService()

        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None

        with patch("app.services.delivery.delivery_service.requests.post", return_value=mock_response) as mock_post:
            svc.send_clinical_output(
                to_email="gp@example.com",
                condition_label="Earache",
                pdf_bytes=b"%PDF-fake-content",
                submission_id="abc12345-0000-0000-0000-000000000000",
                submitted_at=datetime(2026, 3, 25, 10, 30, 0, tzinfo=timezone.utc),
            )

        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        assert "api.eu.mailgun.net" in call_kwargs.args[0]
        assert "mail.summertownhealthcentrechat.co.uk" in call_kwargs.args[0]

    def test_send_uses_correct_auth(self):
        with patch.dict(os.environ, _MAILGUN_ENV, clear=True):
            svc = MailgunHttpDeliveryService()

        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None

        with patch("app.services.delivery.delivery_service.requests.post", return_value=mock_response) as mock_post:
            svc.send_clinical_output(
                to_email="gp@example.com",
                condition_label="Earache",
                pdf_bytes=b"%PDF-fake-content",
                submission_id="abc12345-0000-0000-0000-000000000000",
                submitted_at=datetime(2026, 3, 25, 10, 30, 0, tzinfo=timezone.utc),
            )

        call_kwargs = mock_post.call_args
        assert call_kwargs.kwargs["auth"] == ("api", "key-test123")

    def test_send_includes_pdf_attachment(self):
        with patch.dict(os.environ, _MAILGUN_ENV, clear=True):
            svc = MailgunHttpDeliveryService()

        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None

        with patch("app.services.delivery.delivery_service.requests.post", return_value=mock_response) as mock_post:
            svc.send_clinical_output(
                to_email="gp@example.com",
                condition_label="Earache",
                pdf_bytes=b"%PDF-fake-content",
                submission_id="abc12345-0000-0000-0000-000000000000",
                submitted_at=datetime(2026, 3, 25, 10, 30, 0, tzinfo=timezone.utc),
            )

        call_kwargs = mock_post.call_args
        files = call_kwargs.kwargs["files"]
        filename, content, mimetype = files["attachment"]
        assert filename.endswith(".pdf")
        assert content == b"%PDF-fake-content"
        assert mimetype == "application/pdf"

    def test_send_raises_email_delivery_error_on_http_failure(self):
        import requests as req

        with patch.dict(os.environ, _MAILGUN_ENV, clear=True):
            svc = MailgunHttpDeliveryService()

        with patch("app.services.delivery.delivery_service.requests.post", side_effect=req.RequestException("timeout")):
            with pytest.raises(EmailDeliveryError):
                svc.send_clinical_output(
                    to_email="gp@example.com",
                    condition_label="Earache",
                    pdf_bytes=b"%PDF-fake-content",
                    submission_id="abc12345-0000-0000-0000-000000000000",
                    submitted_at=datetime(2026, 3, 25, 10, 30, 0, tzinfo=timezone.utc),
                )

    def test_send_raises_email_delivery_error_on_bad_status(self):
        import requests as req

        with patch.dict(os.environ, _MAILGUN_ENV, clear=True):
            svc = MailgunHttpDeliveryService()

        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = req.HTTPError("401 Unauthorized")

        with patch("app.services.delivery.delivery_service.requests.post", return_value=mock_response):
            with pytest.raises(EmailDeliveryError):
                svc.send_clinical_output(
                    to_email="gp@example.com",
                    condition_label="Earache",
                    pdf_bytes=b"%PDF-fake-content",
                    submission_id="abc12345-0000-0000-0000-000000000000",
                    submitted_at=datetime(2026, 3, 25, 10, 30, 0, tzinfo=timezone.utc),
                )
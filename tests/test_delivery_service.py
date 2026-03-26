"""
Unit tests for delivery_service.py.

Tests the static email body format and ConsoleDeliveryService behaviour.
No database or SMTP connection required.
"""

import os
import logging
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from app.services.delivery_service import (
    ConsoleDeliveryService,
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
        # These strings should never appear in the static body.
        # They were present in the old format which included ClinicalOutput.
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

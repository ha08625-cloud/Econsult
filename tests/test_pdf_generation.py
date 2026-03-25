# tests/test_pdf_formatter.py
from datetime import datetime, timezone
from app.models.serialisation_contracts import ClinicalOutput, PatientDetails
from app.utils.pdf_formatter import generate_pdf


def test_generate_pdf_returns_valid_pdf_bytes():
    patient = PatientDetails(
        patient_for="me",
        first_name="Jane",
        last_name="Smith",
        date_of_birth="1985-06-15",
        postcode="OX1 1AA",
    )
    clinical = ClinicalOutput(
        condition_id="test_condition",
        free_text="Some symptoms",
        additional_text=None,
        answers={"q1": True, "q2": False, "q3": None},
        safety_messages=[{"id": "S1", "text": "Seek urgent care"}],
        question_labels={"q1": "Do you have a fever?", "q2": "Any chest pain?", "q3": "Shortness of breath?"},
        patient_details=patient,
        contact_preferences={"contact_methods": ["phone"], "phone_number": "07700900000"},
    )

    result = generate_pdf(
        condition_label="Test Condition",
        clinical_output=clinical,
        submission_id="abc12345-0000-0000-0000-000000000000",
        submitted_at=datetime(2026, 3, 23, 14, 0, 0, tzinfo=timezone.utc),
        practice_name="Anytown Medical Practice",
    )

    assert isinstance(result, bytes)
    assert len(result) > 0
    assert result[:4] == b"%PDF"
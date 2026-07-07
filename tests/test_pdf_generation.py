# tests/test_pdf_formatter.py
import contextlib
from datetime import UTC, datetime
import re
import zlib

import pytest

from app.models.serialisation_contracts import ClinicalOutput, PatientDetails
from app.utils.pdf_formatter import generate_pdf

# ---------------------------------------------------------------------------
# Shared test fixtures
# ---------------------------------------------------------------------------

# Length: 631 bytes
# Header bytes: ffd8ffe0

MINIMAL_JPEG: bytes = bytes(
    [
        0xFF,
        0xD8,
        0xFF,
        0xE0,
        0x00,
        0x10,
        0x4A,
        0x46,
        0x49,
        0x46,
        0x00,
        0x01,
        0x01,
        0x00,
        0x00,
        0x01,
        0x00,
        0x01,
        0x00,
        0x00,
        0xFF,
        0xDB,
        0x00,
        0x43,
        0x00,
        0x08,
        0x06,
        0x06,
        0x07,
        0x06,
        0x05,
        0x08,
        0x07,
        0x07,
        0x07,
        0x09,
        0x09,
        0x08,
        0x0A,
        0x0C,
        0x14,
        0x0D,
        0x0C,
        0x0B,
        0x0B,
        0x0C,
        0x19,
        0x12,
        0x13,
        0x0F,
        0x14,
        0x1D,
        0x1A,
        0x1F,
        0x1E,
        0x1D,
        0x1A,
        0x1C,
        0x1C,
        0x20,
        0x24,
        0x2E,
        0x27,
        0x20,
        0x22,
        0x2C,
        0x23,
        0x1C,
        0x1C,
        0x28,
        0x37,
        0x29,
        0x2C,
        0x30,
        0x31,
        0x34,
        0x34,
        0x34,
        0x1F,
        0x27,
        0x39,
        0x3D,
        0x38,
        0x32,
        0x3C,
        0x2E,
        0x33,
        0x34,
        0x32,
        0xFF,
        0xDB,
        0x00,
        0x43,
        0x01,
        0x09,
        0x09,
        0x09,
        0x0C,
        0x0B,
        0x0C,
        0x18,
        0x0D,
        0x0D,
        0x18,
        0x32,
        0x21,
        0x1C,
        0x21,
        0x32,
        0x32,
        0x32,
        0x32,
        0x32,
        0x32,
        0x32,
        0x32,
        0x32,
        0x32,
        0x32,
        0x32,
        0x32,
        0x32,
        0x32,
        0x32,
        0x32,
        0x32,
        0x32,
        0x32,
        0x32,
        0x32,
        0x32,
        0x32,
        0x32,
        0x32,
        0x32,
        0x32,
        0x32,
        0x32,
        0x32,
        0x32,
        0x32,
        0x32,
        0x32,
        0x32,
        0x32,
        0x32,
        0x32,
        0x32,
        0x32,
        0x32,
        0x32,
        0x32,
        0x32,
        0x32,
        0x32,
        0x32,
        0x32,
        0x32,
        0xFF,
        0xC0,
        0x00,
        0x11,
        0x08,
        0x00,
        0x01,
        0x00,
        0x01,
        0x03,
        0x01,
        0x22,
        0x00,
        0x02,
        0x11,
        0x01,
        0x03,
        0x11,
        0x01,
        0xFF,
        0xC4,
        0x00,
        0x1F,
        0x00,
        0x00,
        0x01,
        0x05,
        0x01,
        0x01,
        0x01,
        0x01,
        0x01,
        0x01,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x01,
        0x02,
        0x03,
        0x04,
        0x05,
        0x06,
        0x07,
        0x08,
        0x09,
        0x0A,
        0x0B,
        0xFF,
        0xC4,
        0x00,
        0xB5,
        0x10,
        0x00,
        0x02,
        0x01,
        0x03,
        0x03,
        0x02,
        0x04,
        0x03,
        0x05,
        0x05,
        0x04,
        0x04,
        0x00,
        0x00,
        0x01,
        0x7D,
        0x01,
        0x02,
        0x03,
        0x00,
        0x04,
        0x11,
        0x05,
        0x12,
        0x21,
        0x31,
        0x41,
        0x06,
        0x13,
        0x51,
        0x61,
        0x07,
        0x22,
        0x71,
        0x14,
        0x32,
        0x81,
        0x91,
        0xA1,
        0x08,
        0x23,
        0x42,
        0xB1,
        0xC1,
        0x15,
        0x52,
        0xD1,
        0xF0,
        0x24,
        0x33,
        0x62,
        0x72,
        0x82,
        0x09,
        0x0A,
        0x16,
        0x17,
        0x18,
        0x19,
        0x1A,
        0x25,
        0x26,
        0x27,
        0x28,
        0x29,
        0x2A,
        0x34,
        0x35,
        0x36,
        0x37,
        0x38,
        0x39,
        0x3A,
        0x43,
        0x44,
        0x45,
        0x46,
        0x47,
        0x48,
        0x49,
        0x4A,
        0x53,
        0x54,
        0x55,
        0x56,
        0x57,
        0x58,
        0x59,
        0x5A,
        0x63,
        0x64,
        0x65,
        0x66,
        0x67,
        0x68,
        0x69,
        0x6A,
        0x73,
        0x74,
        0x75,
        0x76,
        0x77,
        0x78,
        0x79,
        0x7A,
        0x83,
        0x84,
        0x85,
        0x86,
        0x87,
        0x88,
        0x89,
        0x8A,
        0x92,
        0x93,
        0x94,
        0x95,
        0x96,
        0x97,
        0x98,
        0x99,
        0x9A,
        0xA2,
        0xA3,
        0xA4,
        0xA5,
        0xA6,
        0xA7,
        0xA8,
        0xA9,
        0xAA,
        0xB2,
        0xB3,
        0xB4,
        0xB5,
        0xB6,
        0xB7,
        0xB8,
        0xB9,
        0xBA,
        0xC2,
        0xC3,
        0xC4,
        0xC5,
        0xC6,
        0xC7,
        0xC8,
        0xC9,
        0xCA,
        0xD2,
        0xD3,
        0xD4,
        0xD5,
        0xD6,
        0xD7,
        0xD8,
        0xD9,
        0xDA,
        0xE1,
        0xE2,
        0xE3,
        0xE4,
        0xE5,
        0xE6,
        0xE7,
        0xE8,
        0xE9,
        0xEA,
        0xF1,
        0xF2,
        0xF3,
        0xF4,
        0xF5,
        0xF6,
        0xF7,
        0xF8,
        0xF9,
        0xFA,
        0xFF,
        0xC4,
        0x00,
        0x1F,
        0x01,
        0x00,
        0x03,
        0x01,
        0x01,
        0x01,
        0x01,
        0x01,
        0x01,
        0x01,
        0x01,
        0x01,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x00,
        0x01,
        0x02,
        0x03,
        0x04,
        0x05,
        0x06,
        0x07,
        0x08,
        0x09,
        0x0A,
        0x0B,
        0xFF,
        0xC4,
        0x00,
        0xB5,
        0x11,
        0x00,
        0x02,
        0x01,
        0x02,
        0x04,
        0x04,
        0x03,
        0x04,
        0x07,
        0x05,
        0x04,
        0x04,
        0x00,
        0x01,
        0x02,
        0x77,
        0x00,
        0x01,
        0x02,
        0x03,
        0x11,
        0x04,
        0x05,
        0x21,
        0x31,
        0x06,
        0x12,
        0x41,
        0x51,
        0x07,
        0x61,
        0x71,
        0x13,
        0x22,
        0x32,
        0x81,
        0x08,
        0x14,
        0x42,
        0x91,
        0xA1,
        0xB1,
        0xC1,
        0x09,
        0x23,
        0x33,
        0x52,
        0xF0,
        0x15,
        0x62,
        0x72,
        0xD1,
        0x0A,
        0x16,
        0x24,
        0x34,
        0xE1,
        0x25,
        0xF1,
        0x17,
        0x18,
        0x19,
        0x1A,
        0x26,
        0x27,
        0x28,
        0x29,
        0x2A,
        0x35,
        0x36,
        0x37,
        0x38,
        0x39,
        0x3A,
        0x43,
        0x44,
        0x45,
        0x46,
        0x47,
        0x48,
        0x49,
        0x4A,
        0x53,
        0x54,
        0x55,
        0x56,
        0x57,
        0x58,
        0x59,
        0x5A,
        0x63,
        0x64,
        0x65,
        0x66,
        0x67,
        0x68,
        0x69,
        0x6A,
        0x73,
        0x74,
        0x75,
        0x76,
        0x77,
        0x78,
        0x79,
        0x7A,
        0x82,
        0x83,
        0x84,
        0x85,
        0x86,
        0x87,
        0x88,
        0x89,
        0x8A,
        0x92,
        0x93,
        0x94,
        0x95,
        0x96,
        0x97,
        0x98,
        0x99,
        0x9A,
        0xA2,
        0xA3,
        0xA4,
        0xA5,
        0xA6,
        0xA7,
        0xA8,
        0xA9,
        0xAA,
        0xB2,
        0xB3,
        0xB4,
        0xB5,
        0xB6,
        0xB7,
        0xB8,
        0xB9,
        0xBA,
        0xC2,
        0xC3,
        0xC4,
        0xC5,
        0xC6,
        0xC7,
        0xC8,
        0xC9,
        0xCA,
        0xD2,
        0xD3,
        0xD4,
        0xD5,
        0xD6,
        0xD7,
        0xD8,
        0xD9,
        0xDA,
        0xE2,
        0xE3,
        0xE4,
        0xE5,
        0xE6,
        0xE7,
        0xE8,
        0xE9,
        0xEA,
        0xF2,
        0xF3,
        0xF4,
        0xF5,
        0xF6,
        0xF7,
        0xF8,
        0xF9,
        0xFA,
        0xFF,
        0xDA,
        0x00,
        0x0C,
        0x03,
        0x01,
        0x00,
        0x02,
        0x11,
        0x03,
        0x11,
        0x00,
        0x3F,
        0x00,
        0xF7,
        0xFA,
        0x28,
        0xA2,
        0x80,
        0x3F,
        0xFF,
        0xD9,
    ]
)


# ---------------------------------------------------------------------------
# PDF text extraction helper
# ---------------------------------------------------------------------------


def extract_pdf_text(pdf_bytes: bytes) -> str:
    """
    Extract human-readable text from a PDF by decompressing all FlateDecode
    content streams and decoding with latin-1.

    FPDF2 compresses content streams with zlib (FlateDecode). Decoding the raw
    bytes with latin-1 only returns the compressed binary, not the text. This
    function finds every stream block in the PDF, attempts zlib decompression,
    and concatenates the results.

    Uses only stdlib (zlib, re) — no third-party PDF library required.
    """
    stream_pattern = re.compile(rb"stream\r?\n(.*?)\r?\nendstream", re.DOTALL)
    parts = []
    for match in stream_pattern.finditer(pdf_bytes):
        raw = match.group(1)
        with contextlib.suppress(zlib.error):
            parts.append(zlib.decompress(raw).decode("latin-1"))

    return "\n".join(parts)

# ---------------------------------------------------------------------------
# Shared test fixtures
# ---------------------------------------------------------------------------


def _make_patient(
    gender: str = "female",
    preferred_name: str | None = None,
    nhs_number: str | None = None,
    dob: str = "1985-06-15",
) -> PatientDetails:
    return PatientDetails(
        patient_for="me",
        first_name="Jane",
        last_name="Smith",
        date_of_birth=dob,
        postcode="OX1 1AA",
        gender=gender,
        preferred_name=preferred_name,
        nhs_number=nhs_number,
    )


@pytest.fixture
def minimal_clinical_output() -> ClinicalOutput:
    return ClinicalOutput(
        condition_id="test_condition",
        free_text="Some symptoms",
        additional_text=None,
        answers={"q1": True, "q2": False, "q3": None},
        safety_messages=[{"id": "S1", "text": "Seek urgent care"}],
        question_labels={
            "q1": "Do you have a fever?",
            "q2": "Any chest pain?",
            "q3": "Shortness of breath?",
        },
        patient_details=_make_patient(),
        contact_preferences={"contact_methods": ["phone"], "phone_number": "07700900000"},
    )


@pytest.fixture
def submission_kwargs() -> dict:
    return dict(
        condition_label="Test Condition",
        submission_id="abc12345-0000-0000-0000-000000000000",
        submitted_at=datetime(2026, 3, 23, 14, 0, 0, tzinfo=UTC),
        practice_name="Anytown Medical Practice",
    )


# ---------------------------------------------------------------------------
# Existing tests (unchanged behaviour)
# ---------------------------------------------------------------------------


def test_generate_pdf_returns_valid_pdf_bytes(minimal_clinical_output, submission_kwargs):
    result = generate_pdf(clinical_output=minimal_clinical_output, **submission_kwargs)

    assert isinstance(result, bytes)
    assert len(result) > 0
    assert result[:4] == b"%PDF"


# ---------------------------------------------------------------------------
# Photo embedding tests
# ---------------------------------------------------------------------------


def test_generate_pdf_with_photo_bytes_none_returns_valid_pdf(
    minimal_clinical_output, submission_kwargs
):
    """photo_bytes=None must produce a valid PDF identical in behaviour to omitting the argument."""
    result = generate_pdf(
        clinical_output=minimal_clinical_output,
        photo_bytes=None,
        **submission_kwargs,
    )
    assert result[:4] == b"%PDF"


def test_generate_pdf_with_empty_photo_list_returns_valid_pdf(
    minimal_clinical_output, submission_kwargs
):
    """photo_bytes=[] must produce a valid PDF. No PHOTOS section should be added."""
    result = generate_pdf(
        clinical_output=minimal_clinical_output,
        photo_bytes=[],
        **submission_kwargs,
    )
    assert result[:4] == b"%PDF"


def test_generate_pdf_with_photos_returns_valid_pdf(minimal_clinical_output, submission_kwargs):
    """A real minimal JPEG must be embedded without raising."""
    result = generate_pdf(
        clinical_output=minimal_clinical_output,
        photo_bytes=[MINIMAL_JPEG],
        **submission_kwargs,
    )
    assert result[:4] == b"%PDF"


def test_generate_pdf_with_photos_is_larger_than_without(
    minimal_clinical_output, submission_kwargs
):
    """A PDF with an embedded photo must be strictly larger than one without."""
    without_photos = generate_pdf(
        clinical_output=minimal_clinical_output,
        photo_bytes=None,
        **submission_kwargs,
    )
    with_photos = generate_pdf(
        clinical_output=minimal_clinical_output,
        photo_bytes=[MINIMAL_JPEG],
        **submission_kwargs,
    )
    assert len(with_photos) > len(without_photos)


def test_generate_pdf_no_photos_and_empty_list_same_size(
    minimal_clinical_output, submission_kwargs
):
    """photo_bytes=None and photo_bytes=[] must produce output of the same size.
    Both mean no photos; neither should add a PHOTOS section."""
    none_result = generate_pdf(
        clinical_output=minimal_clinical_output,
        photo_bytes=None,
        **submission_kwargs,
    )
    empty_result = generate_pdf(
        clinical_output=minimal_clinical_output,
        photo_bytes=[],
        **submission_kwargs,
    )
    assert len(none_result) == len(empty_result)


# ---------------------------------------------------------------------------
# Consultation outcome in PDF tests
# ---------------------------------------------------------------------------


def _make_output_with_outcome(outcome: str | None) -> ClinicalOutput:
    cp: dict = {
        "contact_methods": ["email"],
        "email_address": "patient@example.com",
        "doctor_preference": "any",
    }
    if outcome is not None:
        cp["consultation_outcome"] = outcome

    return ClinicalOutput(
        condition_id="test_condition",
        free_text="Some symptoms",
        additional_text=None,
        answers={},
        safety_messages=[],
        question_labels={},
        patient_details=_make_patient(),
        contact_preferences=cp,
    )


def test_consultation_outcome_appears_in_pdf(submission_kwargs):
    """A known outcome value must appear as its human-readable label in the PDF."""
    output = _make_output_with_outcome("face_to_face")
    result = generate_pdf(clinical_output=output, **submission_kwargs)
    pdf_text = extract_pdf_text(result)
    assert "A face to face appointment" in pdf_text
    assert "Consultation outcome:" in pdf_text


def test_all_outcome_values_render_with_known_label(submission_kwargs):
    """Every valid outcome value must render its human-readable label, not the raw value."""
    outcomes = {
        "admin_task": "Administrative task only",
        "face_to_face": "A face to face appointment",
        "phone_appointment": "A phone appointment",
        "advice_only": "Medical advice by text or email only",
        "medication": "Medication request or query",
        "not_sure": "Not sure",
    }
    for value, expected_fragment in outcomes.items():
        output = _make_output_with_outcome(value)
        result = generate_pdf(clinical_output=output, **submission_kwargs)
        pdf_text = extract_pdf_text(result)
        assert expected_fragment in pdf_text, (
            f"Expected label fragment {expected_fragment!r} for outcome {value!r} not found in PDF"
        )


def test_absent_outcome_produces_no_outcome_row(submission_kwargs):
    """When consultation_outcome is absent from contact_preferences, no outcome row is rendered."""
    output = _make_output_with_outcome(None)
    result = generate_pdf(clinical_output=output, **submission_kwargs)
    pdf_text = extract_pdf_text(result)
    assert "Consultation outcome:" not in pdf_text


def test_null_outcome_produces_no_outcome_row(submission_kwargs):
    """When consultation_outcome is explicitly None, no outcome row is rendered."""
    output = ClinicalOutput(
        condition_id="test_condition",
        free_text="Some symptoms",
        additional_text=None,
        answers={},
        safety_messages=[],
        question_labels={},
        patient_details=_make_patient(),
        contact_preferences={
            "contact_methods": ["email"],
            "email_address": "patient@example.com",
            "doctor_preference": "any",
            "consultation_outcome": None,
        },
    )
    result = generate_pdf(clinical_output=output, **submission_kwargs)
    pdf_text = extract_pdf_text(result)
    assert "Consultation outcome:" not in pdf_text


# ---------------------------------------------------------------------------
# New patient detail field tests
# ---------------------------------------------------------------------------


def test_gender_label_appears_in_patient_summary(submission_kwargs):
    """Gender must appear as a human-readable label in the patient summary line."""
    output = ClinicalOutput(
        condition_id="test_condition",
        free_text="symptoms",
        additional_text=None,
        answers={},
        safety_messages=[],
        question_labels={},
        patient_details=_make_patient(gender="male"),
        contact_preferences=None,
    )
    result = generate_pdf(clinical_output=output, **submission_kwargs)
    pdf_text = extract_pdf_text(result)
    assert "Male" in pdf_text


def test_prefer_not_to_say_renders_human_readable(submission_kwargs):
    """prefer_not_to_say must render as 'Prefer not to say', not the raw value."""
    output = ClinicalOutput(
        condition_id="test_condition",
        free_text="symptoms",
        additional_text=None,
        answers={},
        safety_messages=[],
        question_labels={},
        patient_details=_make_patient(gender="prefer_not_to_say"),
        contact_preferences=None,
    )
    result = generate_pdf(clinical_output=output, **submission_kwargs)
    pdf_text = extract_pdf_text(result)
    assert "Prefer not to say" in pdf_text
    assert "prefer_not_to_say" not in pdf_text


def test_age_appears_in_patient_summary(submission_kwargs):
    """Age in whole years must appear in the patient summary line."""
    # DOB 1985-06-15. Submitted at 2026-03-23. Age = 40 (birthday not yet reached in 2026).
    output = ClinicalOutput(
        condition_id="test_condition",
        free_text="symptoms",
        additional_text=None,
        answers={},
        safety_messages=[],
        question_labels={},
        patient_details=_make_patient(dob="1985-06-15"),
        contact_preferences=None,
    )
    result = generate_pdf(clinical_output=output, **submission_kwargs)
    pdf_text = extract_pdf_text(result)
    assert "40" in pdf_text


def test_preferred_name_appears_when_set(submission_kwargs):
    """Preferred name row must appear in the PDF when a preferred name is provided."""
    output = ClinicalOutput(
        condition_id="test_condition",
        free_text="symptoms",
        additional_text=None,
        answers={},
        safety_messages=[],
        question_labels={},
        patient_details=_make_patient(preferred_name="Jo"),
        contact_preferences=None,
    )
    result = generate_pdf(clinical_output=output, **submission_kwargs)
    pdf_text = extract_pdf_text(result)
    assert "Preferred name:" in pdf_text
    assert "Jo" in pdf_text


def test_preferred_name_absent_when_not_set(submission_kwargs):
    """Preferred name row must not appear when preferred_name is None."""
    output = ClinicalOutput(
        condition_id="test_condition",
        free_text="symptoms",
        additional_text=None,
        answers={},
        safety_messages=[],
        question_labels={},
        patient_details=_make_patient(preferred_name=None),
        contact_preferences=None,
    )
    result = generate_pdf(clinical_output=output, **submission_kwargs)
    pdf_text = extract_pdf_text(result)
    assert "Preferred name:" not in pdf_text


def test_nhs_number_appears_with_standard_spacing(submission_kwargs):
    """NHS number must appear formatted as 'NNN NNN NNNN'."""
    output = ClinicalOutput(
        condition_id="test_condition",
        free_text="symptoms",
        additional_text=None,
        answers={},
        safety_messages=[],
        question_labels={},
        patient_details=_make_patient(nhs_number="4857773456"),
        contact_preferences=None,
    )
    result = generate_pdf(clinical_output=output, **submission_kwargs)
    pdf_text = extract_pdf_text(result)
    assert "NHS number:" in pdf_text
    assert "485 777 3456" in pdf_text


def test_nhs_number_absent_when_not_set(submission_kwargs):
    """NHS number row must not appear when nhs_number is None."""
    output = ClinicalOutput(
        condition_id="test_condition",
        free_text="symptoms",
        additional_text=None,
        answers={},
        safety_messages=[],
        question_labels={},
        patient_details=_make_patient(nhs_number=None),
        contact_preferences=None,
    )
    result = generate_pdf(clinical_output=output, **submission_kwargs)
    pdf_text = extract_pdf_text(result)
    assert "NHS number:" not in pdf_text


# ---------------------------------------------------------------------------
# Quantity (unit-toggle) answer rendering
#
# Imperial renders "11 st 11 lb (74.8 kg)"; metric renders the typed kilograms
# verbatim. The canonical value is already rounded; the formatter renders it at
# decimal_places. Extraction asserts the raw and kg fragments separately, since
# they are robust to any cell-internal text chunking.
# ---------------------------------------------------------------------------


def _quantity_output(unit_system, answer_value, raw_components, decimal_places=1):
    return ClinicalOutput(
        condition_id="numeric_capability_demo",
        free_text="symptoms",
        additional_text=None,
        answers={"patient_weight_kg": answer_value},
        safety_messages=[],
        question_labels={"patient_weight_kg": "What is your current weight?"},
        patient_details=_make_patient(),
        contact_preferences=None,
        unit_system=unit_system,
        quantity_answers={
            "patient_weight_kg": {
                "raw_components": raw_components,
                "decimal_places": decimal_places,
            }
        },
    )


def test_imperial_quantity_renders_stones_pounds_and_kg(submission_kwargs):
    output = _quantity_output("imperial", "74.8", {"st": 11, "lb": 11})
    pdf_text = extract_pdf_text(generate_pdf(clinical_output=output, **submission_kwargs))
    assert "11 st 11 lb" in pdf_text
    assert "74.8 kg" in pdf_text


def test_imperial_quantity_zero_decimal_places_rounds_whole(submission_kwargs):
    output = _quantity_output("imperial", "75", {"st": 11, "lb": 11}, decimal_places=0)
    pdf_text = extract_pdf_text(generate_pdf(clinical_output=output, **submission_kwargs))
    assert "11 st 11 lb" in pdf_text
    assert "75 kg" in pdf_text


def test_metric_quantity_renders_kilograms_verbatim(submission_kwargs):
    output = _quantity_output("metric", "70.5", {"kg": "70.5"})
    pdf_text = extract_pdf_text(generate_pdf(clinical_output=output, **submission_kwargs))
    assert "70.5 kg" in pdf_text
    # No imperial render: the " lb (" marker only appears in the stones/pounds form.
    assert " lb (" not in pdf_text


def test_non_quantity_answer_still_renders_yes_no(submission_kwargs):
    # Regression: a normal boolean answer is unaffected by the quantity branch.
    output = ClinicalOutput(
        condition_id="test_condition",
        free_text="symptoms",
        additional_text=None,
        answers={"q1": True},
        safety_messages=[],
        question_labels={"q1": "Do you have a fever?"},
        patient_details=_make_patient(),
        contact_preferences=None,
    )
    pdf_text = extract_pdf_text(generate_pdf(clinical_output=output, **submission_kwargs))
    assert "Yes" in pdf_text

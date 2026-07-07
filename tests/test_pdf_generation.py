# tests/test_pdf_formatter.py
import contextlib
import re
import zlib
from datetime import UTC, datetime

import pytest

from app.models.serialisation_contracts import ClinicalOutput, PatientDetails
from app.utils.pdf_formatter import generate_pdf
from tests.helpers.image_utils import get_minimal_jpeg_bytes

# ---------------------------------------------------------------------------
# Shared test fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def minimal_jpeg() -> bytes:
    """
    Yields the minimal JPEG bytes. 
    Scoped to session so the file is only read from disk once per test run.
    """
    return get_minimal_jpeg_bytes()

# ... [Keep your _make_patient, minimal_clinical_output, etc.] ...

# ---------------------------------------------------------------------------
# Photo embedding tests
# ---------------------------------------------------------------------------

# Update your tests to request the `minimal_jpeg` fixture:

def test_generate_pdf_with_photos_returns_valid_pdf(
    minimal_clinical_output, submission_kwargs, minimal_jpeg
):
    """A real minimal JPEG must be embedded without raising."""
    result = generate_pdf(
        clinical_output=minimal_clinical_output,
        photo_bytes=[minimal_jpeg],
        **submission_kwargs,
    )
    assert result[:4] == b"%PDF"


def test_generate_pdf_with_photos_is_larger_than_without(
    minimal_clinical_output, submission_kwargs, minimal_jpeg
):
    """A PDF with an embedded photo must be strictly larger than one without."""
    without_photos = generate_pdf(
        clinical_output=minimal_clinical_output,
        photo_bytes=None,
        **submission_kwargs,
    )
    with_photos = generate_pdf(
        clinical_output=minimal_clinical_output,
        photo_bytes=[minimal_jpeg],
        **submission_kwargs,
    )
    assert len(with_photos) > len(without_photos)

# ... [Rest of your tests remain unchanged] ...

"""
Unit tests for app/utils/image_sanitizer.py

These tests exercise sanitize_image() in isolation, with no database or HTTP
layer involved. They verify:

  - Valid JPEG input returns JPEG output.
  - Valid PNG input is converted to JPEG output (format normalisation).
  - EXIF metadata is stripped from the output.
  - Truncated JPEG input raises ValueError.
  - Bytes with no recognisable image structure raise ValueError.

A minimal valid PNG is constructed programmatically via Pillow rather than
hardcoding raw bytes, to keep the fixture readable and maintainable.
"""

import io
import struct
import zlib

import pytest
from PIL import Image

from app.utils.image_sanitizer import sanitize_image
from tests.test_pdf_generation import MINIMAL_JPEG

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_minimal_png() -> bytes:
    """
    Build a 1x1 pixel red PNG using Pillow.
    This is the canonical way to produce a valid minimal PNG — constructing
    one from raw bytes requires reproducing the full chunk/CRC structure,
    which is fragile and adds no test value.
    """
    img = Image.new("RGB", (1, 1), color=(255, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_jpeg_with_exif() -> bytes:
    """
    Build a minimal JPEG with a synthetic EXIF APP1 marker inserted immediately
    after the SOI marker.

    JPEG structure:
      FF D8          — SOI (start of image)
      FF E1 LL LL    — APP1 marker + 2-byte big-endian length (includes the 2 length bytes)
      [payload]      — EXIF data (we use a short synthetic block)
      [rest]         — remainder of the base JPEG

    We insert the APP1 block after the SOI bytes of MINIMAL_JPEG. The
    sanitizer must strip it during re-encoding.

    The APP1 length field = len(payload) + 2 (the +2 accounts for the length
    field itself, per the JFIF/EXIF convention).
    """
    # Synthetic EXIF payload — content does not need to be valid EXIF,
    # only the marker bytes matter for the assertion.
    fake_exif_payload = b"Exif\x00\x00" + b"\x00" * 10

    length = len(fake_exif_payload) + 2  # +2 for the length field itself
    app1_segment = b"\xff\xe1" + struct.pack(">H", length) + fake_exif_payload

    # MINIMAL_JPEG starts with FF D8 (SOI), then FF E0 (APP0/JFIF marker).
    # We insert our APP1 segment after the SOI bytes (first 2 bytes).
    soi = MINIMAL_JPEG[:2]
    rest = MINIMAL_JPEG[2:]
    return soi + app1_segment + rest


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_sanitize_valid_jpeg_returns_bytes():
    """
    A valid JPEG input must produce non-empty bytes output.
    """
    result = sanitize_image(MINIMAL_JPEG)
    assert isinstance(result, bytes)
    assert len(result) > 0


def test_sanitize_valid_jpeg_output_is_jpeg():
    """
    Output must begin with the JPEG SOI magic bytes (FF D8 FF).
    """
    result = sanitize_image(MINIMAL_JPEG)
    assert result[:3] == b"\xff\xd8\xff", (
        "Expected sanitized JPEG output to start with FF D8 FF"
    )


def test_sanitize_valid_png_returns_jpeg():
    """
    PNG input must be converted to JPEG output (format normalisation).
    Confirmed by checking the JPEG SOI magic bytes on the output.
    """
    png_bytes = _make_minimal_png()
    result = sanitize_image(png_bytes)
    assert result[:3] == b"\xff\xd8\xff", (
        "Expected PNG input to be normalised to JPEG output (FF D8 FF)"
    )


def test_sanitize_strips_exif():
    """
    An image with a synthetic EXIF APP1 segment (FF E1) must produce output
    that contains no APP1 marker bytes.

    CDR strips metadata by re-encoding from the decoded pixel buffer. Pillow
    does not carry EXIF through convert("RGB") -> save(..., format="JPEG")
    when no exif= argument is passed to save(). The APP1 marker in the output
    would only appear if Pillow explicitly wrote one.
    """
    jpeg_with_exif = _make_jpeg_with_exif()

    # Confirm the input actually contains an APP1 marker before sanitizing.
    assert b"\xff\xe1" in jpeg_with_exif, (
        "Test setup error: input JPEG does not contain an APP1 marker"
    )

    result = sanitize_image(jpeg_with_exif)

    assert b"\xff\xe1" not in result, (
        "Expected EXIF APP1 marker (FF E1) to be absent from sanitized output"
    )


def test_sanitize_truncated_jpeg_raises():
    """
    A truncated JPEG — valid SOI header, abrupt end — must raise ValueError.

    This is the CDR regression test for CE+. The old verify() call (header-only)
    would pass these bytes because the SOI and minimal segment headers are
    present. The new CDR path calls convert("RGB"), which triggers a full decode
    and will raise on the missing image data.

    Structural note: this same full-decode property structurally neutralises
    polyglot files. A polyglot typically embeds a second payload in regions
    Pillow ignores (e.g. appended bytes after the JPEG EOI marker, or padding
    in unused header space). Because CDR re-encodes the image from the decoded
    pixel buffer rather than forwarding the original bytes, any such appended
    payload is simply not present in the output — it never reaches the database
    or the PDF worker. There is no need to construct a specific polyglot payload
    to test this property; it follows directly from re-encoding.
    """
    truncated = b"\xff\xd8\xff" + b"\x00" * 16  # valid SOI, then abrupt end

    with pytest.raises(ValueError):
        sanitize_image(truncated)


def test_sanitize_corrupt_bytes_raises():
    """
    Bytes with no recognisable image structure must raise ValueError.
    """
    garbage = b"\x00\x01\x02\x03" * 20

    with pytest.raises(ValueError):
        sanitize_image(garbage)
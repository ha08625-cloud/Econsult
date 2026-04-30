"""
Unit tests for app/utils/image_sanitizer.py

These tests exercise sanitize_image() in isolation, with no database or HTTP
layer involved. They verify:

  - Valid JPEG input returns JPEG output.
  - Valid PNG input is converted to JPEG output (format normalisation).
  - EXIF metadata is stripped from the output.
  - Truncated JPEG input raises ValueError.
  - Bytes with no recognisable image structure raise ValueError.
  - Standard-tier encode produces JPEG output.
  - High-tier encode produces JPEG output.
  - Neither tier upscales an image already within its bounds.
  - High-tier applies quality iteration when the initial encode exceeds 5 MB.
  - A source image that cannot be reduced below 5 MB raises ImageTooLargeError.

A minimal valid PNG is constructed programmatically via Pillow rather than
hardcoding raw bytes, to keep the fixture readable and maintainable.
"""

import io
import struct

import pytest
from PIL import Image

from app.utils.image_sanitizer import ImageTooLargeError, sanitize_image
from tests.test_pdf_generation import MINIMAL_JPEG

_5MB = 5 * 1024 * 1024

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


def _make_large_jpeg(long_edge_px: int) -> bytes:
    """
    Build a valid JPEG at the given long edge size filled with random-ish
    noise. Noise is incompressible, so the output will be large relative
    to a plain-colour image of the same dimensions — useful for testing
    that the size limit is exercised.

    We use a deterministic pattern rather than os.urandom so tests are
    reproducible. The pattern produces high per-pixel variation which
    defeats JPEG's DCT compression.
    """
    import random
    rng = random.Random(42)
    pixels = bytes(rng.randint(0, 255) for _ in range(long_edge_px * long_edge_px * 3))
    img = Image.frombytes("RGB", (long_edge_px, long_edge_px), pixels)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=95)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Existing tests — no changes to behaviour, preserved verbatim
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


# ---------------------------------------------------------------------------
# Tier tests — output format
# ---------------------------------------------------------------------------

def test_standard_tier_produces_jpeg():
    """
    standard-tier encode must return valid JPEG bytes.
    """
    result = sanitize_image(MINIMAL_JPEG, tier="standard")
    assert result[:3] == b"\xff\xd8\xff", (
        "Expected standard-tier output to be JPEG (FF D8 FF)"
    )


def test_high_tier_produces_jpeg():
    """
    high-tier encode must return valid JPEG bytes.
    """
    result = sanitize_image(MINIMAL_JPEG, tier="high")
    assert result[:3] == b"\xff\xd8\xff", (
        "Expected high-tier output to be JPEG (FF D8 FF)"
    )


def test_unknown_tier_raises_key_error():
    """
    Passing an unrecognised tier string is a programming error and must raise
    KeyError immediately. This is intentional — it surfaces misconfiguration
    at the call site rather than silently applying a default.
    """
    with pytest.raises(KeyError):
        sanitize_image(MINIMAL_JPEG, tier="ultra")


# ---------------------------------------------------------------------------
# Tier tests — resize behaviour
# ---------------------------------------------------------------------------

def test_standard_tier_does_not_upscale_small_image():
    """
    An image smaller than 1920px on its long edge must not be upscaled by
    the standard-tier path. thumbnail() only shrinks, never enlarges.
    """
    # 100x100 is well within the 1920px standard-tier bound.
    small = Image.new("RGB", (100, 100), color=(0, 0, 255))
    buf = io.BytesIO()
    small.save(buf, format="JPEG")
    small_bytes = buf.getvalue()

    result = sanitize_image(small_bytes, tier="standard")

    output_img = Image.open(io.BytesIO(result))
    assert output_img.width <= 100 and output_img.height <= 100, (
        f"standard-tier must not upscale: got {output_img.size}, expected <= (100, 100)"
    )


def test_high_tier_does_not_upscale_small_image():
    """
    An image smaller than 3840px on its long edge must not be upscaled by
    the high-tier path.
    """
    small = Image.new("RGB", (200, 200), color=(0, 255, 0))
    buf = io.BytesIO()
    small.save(buf, format="JPEG")
    small_bytes = buf.getvalue()

    result = sanitize_image(small_bytes, tier="high")

    output_img = Image.open(io.BytesIO(result))
    assert output_img.width <= 200 and output_img.height <= 200, (
        f"high-tier must not upscale: got {output_img.size}, expected <= (200, 200)"
    )


def test_standard_tier_resizes_image_exceeding_1920px():
    """
    An image with a long edge greater than 1920px must be resized down to
    1920px on the long edge by the standard-tier path.
    """
    # 2400x1800: long edge 2400, which exceeds the 1920px standard-tier bound.
    large = Image.new("RGB", (2400, 1800), color=(128, 128, 128))
    buf = io.BytesIO()
    large.save(buf, format="JPEG")
    large_bytes = buf.getvalue()

    result = sanitize_image(large_bytes, tier="standard")

    output_img = Image.open(io.BytesIO(result))
    assert max(output_img.size) <= 1920, (
        f"standard-tier must resize long edge to <= 1920px, got {output_img.size}"
    )


def test_high_tier_resizes_image_exceeding_3840px():
    """
    An image with a long edge greater than 3840px must be resized down to
    3840px on the long edge by the high-tier first attempt.
    """
    # 5000x3000: long edge 5000, which exceeds the 3840px high-tier bound.
    large = Image.new("RGB", (5000, 3000), color=(64, 64, 64))
    buf = io.BytesIO()
    large.save(buf, format="JPEG")
    large_bytes = buf.getvalue()

    result = sanitize_image(large_bytes, tier="high")

    output_img = Image.open(io.BytesIO(result))
    assert max(output_img.size) <= 3840, (
        f"high-tier must resize long edge to <= 3840px, got {output_img.size}"
    )


# ---------------------------------------------------------------------------
# Tier tests — 5 MB size enforcement and iteration
# ---------------------------------------------------------------------------

def test_standard_tier_output_within_5mb():
    """
    standard-tier output must be within the 5 MB EMIS limit for a realistic
    source image. We use a plain-colour source — this is not testing the
    iteration path (standard has none), only that the happy path is safe.
    """
    source = Image.new("RGB", (3000, 2000), color=(100, 150, 200))
    buf = io.BytesIO()
    source.save(buf, format="JPEG", quality=95)

    result = sanitize_image(buf.getvalue(), tier="standard")

    assert len(result) <= _5MB, (
        f"standard-tier output must be <= 5 MB, got {len(result)} bytes"
    )


def test_high_tier_iteration_succeeds_for_compressible_image():
    """
    A large but compressible source image (plain colour) must be reduced
    within 5 MB by the high-tier path, ideally on the first attempt.

    This test confirms the iteration loop terminates successfully and
    returns bytes, without asserting which attempt was used.
    """
    source = Image.new("RGB", (6000, 4000), color=(200, 100, 50))
    buf = io.BytesIO()
    source.save(buf, format="JPEG", quality=95)

    result = sanitize_image(buf.getvalue(), tier="high")

    assert isinstance(result, bytes)
    assert len(result) <= _5MB, (
        f"high-tier output must be <= 5 MB, got {len(result)} bytes"
    )


def test_high_tier_raises_image_too_large_error_when_all_attempts_fail(monkeypatch):
    """
    When all three high-tier encode attempts produce output exceeding 5 MB,
    sanitize_image must raise ImageTooLargeError.

    We monkeypatch io.BytesIO so that every save() call produces a buffer
    whose getvalue() returns bytes just over the 5 MB threshold, simulating
    an image that is too complex to compress below the limit at any of the
    three iteration steps.
    """
    _OVER_LIMIT = _5MB + 1

    original_bytesio = io.BytesIO

    class _FakeSaveBuffer(original_bytesio):
        """
        Intercepts save() calls from Pillow by overriding getvalue().

        We only want to override the save output buffers, not the initial
        Image.open() read buffer. We distinguish them by checking whether
        any bytes were written: Pillow writes to the buffer during save(),
        leaving it non-empty.
        """
        def getvalue(self):
            data = super().getvalue()
            if len(data) > 0:
                # Simulate an oversized encode result.
                return b"\xff\xd8\xff" + b"\x00" * _OVER_LIMIT
            return data

    monkeypatch.setattr(io, "BytesIO", _FakeSaveBuffer)

    with pytest.raises(ImageTooLargeError):
        sanitize_image(MINIMAL_JPEG, tier="high")


def test_image_too_large_error_is_subclass_of_value_error():
    """
    ImageTooLargeError must be a subclass of ValueError so that existing
    callers catching ValueError for corrupt images see it as a ValueError.
    This allows callers to catch ImageTooLargeError first for specific
    handling without breaking the existing error contract.
    """
    assert issubclass(ImageTooLargeError, ValueError), (
        "ImageTooLargeError must inherit from ValueError"
    )

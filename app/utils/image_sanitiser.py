"""
Image sanitizer — Content Disarm and Reconstruction (CDR).

Provides a single public function: sanitize_image(raw_bytes) -> bytes

The sanitizer performs a full decode of the input image via Pillow and
re-encodes it as a clean JPEG. This approach:

  - Catches truncated or corrupt image bodies that pass a header-only
    check (verify()) but fail full decode. These would otherwise reach
    the PDF worker and cause job failure.
  - Strips all metadata, including EXIF, ICC profiles, and any embedded
    content that Pillow does not carry through to the output buffer.
  - Normalises format: input may be JPEG or PNG; output is always JPEG.
    PNG-to-JPEG conversion is lossy at quality 85. This is acceptable
    for this system because PNG uploads are almost always screenshots,
    not clinical photography requiring maximum fidelity.
  - Structurally neutralises polyglot files. A file that embeds a second
    payload in regions Pillow ignores (e.g. after the JPEG EOI marker)
    will have that payload discarded during re-encoding, because Pillow
    only reads the image data it understands and the output buffer is
    written from scratch.

No logging is performed here. The calling layer owns that concern.
"""

import io

from PIL import Image


def sanitize_image(raw_bytes: bytes) -> bytes:
    """
    Perform CDR on raw image bytes.

    Opens the image, converts to RGB (full decode — strips alpha, palette
    modes, and all metadata), and saves to a fresh buffer as JPEG at
    quality 85.

    Args:
        raw_bytes: Raw bytes of the uploaded image.

    Returns:
        Clean JPEG bytes.

    Raises:
        ValueError: If Pillow cannot fully decode the input for any reason.
    """
    try:
        img = Image.open(io.BytesIO(raw_bytes))
        img = img.convert("RGB")
        output = io.BytesIO()
        img.save(output, format="JPEG", quality=85)
        return output.getvalue()
    except Exception as exc:
        raise ValueError("not a valid image") from exc
"""
Image sanitizer — Content Disarm and Reconstruction (CDR).

Provides a single public function: sanitize_image(raw_bytes, tier) -> bytes

The sanitizer performs a full decode of the input image via Pillow and
re-encodes it as a clean JPEG. This approach:

  - Strips all metadata, including EXIF, ICC profiles, and any embedded
    content that Pillow does not carry through to the output buffer.
  - Normalises format to JPEG.
  - Structurally neutralises polyglot files
  - Resizes the image to within the bounds defined by the submission tier,
    and enforces a 5MB post-encode size limit with a quality iteration
    fallback for high-tier submissions.

No logging is performed here. The calling layer owns that concern.
"""

import io

from PIL import Image

# Post-encode size limit imposed by the EMIS EHR ingestion layer.
_EMIS_MAX_BYTES = 5 * 1024 * 1024  # 5 MB

# Tier configuration.
#
# Each tier is a list of (long_edge_px, quality) attempts tried in order.
# The first attempt that produces output within _EMIS_MAX_BYTES is returned.
# If all attempts fail, sanitize_image raises ImageTooLargeError.
#
# "standard" tier: single attempt — 1080p at quality 80 reliably stays within
# 5 MB for any realistic source image, so no iteration is needed.
#
# "high" tier: three attempts in descending quality/resolution order:
#   1. 4K (3840px) quality 85 — full clinical zoom capability
#   2. 4K (3840px) quality 80 — allows ~200% zoom with minimal quality loss
#   3. 2560px quality 85     — allows ~150% zoom with minimal quality loss
# The fallback sequence preserves as much diagnostic quality as possible
# at each step before giving up.
_TIER_ATTEMPTS: dict[str, list[tuple[int, int]]] = {
    "standard": [
        (1920, 80),
    ],
    "high": [
        (3840, 85),
        (3840, 80),
        (2560, 85),
    ],
}


class ImageTooLargeError(ValueError):
    """
    Raised when a high-tier image cannot be reduced below the EMIS 5 MB
    limit by any quality iteration step.

    Inherits from ValueError so that existing callers catching ValueError
    (e.g. for corrupt images) do not silently swallow this error — they
    would need to explicitly catch ImageTooLargeError first if they want
    to handle it differently.
    """


def sanitize_image(raw_bytes: bytes, tier: str = "standard") -> bytes:
    """
    Perform CDR on raw image bytes.

    Decodes the image, converts to RGB (strips alpha, palette modes, and all
    metadata), resizes to within the tier's maximum long edge using
    Image.thumbnail() (which never upscales), then encodes as JPEG.

    For high-tier submissions, if the initial encode exceeds _EMIS_MAX_BYTES,
    the function iterates through fallback (long_edge, quality) pairs before
    raising ImageTooLargeError.

    Standard-tier submissions use a single encode step. The 1080p/quality-80
    combination reliably produces output well within 5 MB for any realistic
    source image.

    Args:
        raw_bytes: Raw bytes of the uploaded image (JPEG or PNG).
        tier:      Submission tier — "standard" (default) or "high".

    Returns:
        Clean JPEG bytes within _EMIS_MAX_BYTES.

    Raises:
        ValueError:         If Pillow cannot fully decode the input.
        ImageTooLargeError: If a high-tier image cannot be reduced below
                            _EMIS_MAX_BYTES by any iteration step.
        KeyError:           If an unrecognised tier value is passed. This is
                            a programming error and should not reach production.
    """
    attempts = _TIER_ATTEMPTS[tier]  # KeyError for unrecognised tier — intentional

    try:
        img = Image.open(io.BytesIO(raw_bytes))
        # convert("RGB") must come before thumbnail(). Calling thumbnail() on
        # a palette-mode or RGBA image can produce unexpected results because
        # Pillow's internal resize path behaves differently per mode.
        img = img.convert("RGB")
    except Exception as exc:
        raise ValueError("not a valid image") from exc

    for long_edge, quality in attempts:
        # thumbnail() resizes in-place so that neither dimension exceeds the
        # given bound. It never upscales — if the image is already within
        # bounds, it is left unchanged. We work on a copy so that each
        # iteration starts from the same converted-RGB source.
        candidate = img.copy()
        candidate.thumbnail((long_edge, long_edge), Image.LANCZOS)

        output = io.BytesIO()
        candidate.save(output, format="JPEG", quality=quality)
        result = output.getvalue()

        if len(result) <= _EMIS_MAX_BYTES:
            return result

    # All attempts exhausted without reaching the size limit.
    raise ImageTooLargeError(
        "Image could not be reduced below the 5 MB limit. "
        "Please check your camera settings — 12MP or lower is recommended. "
        "You can also crop the image before uploading."
    )

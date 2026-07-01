"""
tests/test_mesh_payload.py

Unit tests for the MeshPayloadBuilder seam and the RawPdfPayloadBuilder
implementation.

No database, no network. The builder is a pure function of its inputs so
all coverage is achievable at the unit level.
"""

import dataclasses

import pytest

from app.services.delivery.mesh_payload import (
    MeshPayload,
    RawPdfPayloadBuilder,
)

# ---------------------------------------------------------------------------
# Protocol structural compliance
# ---------------------------------------------------------------------------


def test_raw_pdf_builder_has_protocol_shape():
    """
    RawPdfPayloadBuilder must satisfy the structural shape of
    MeshPayloadBuilder: a callable `build` method accepting keyword-only
    `pdf_bytes` and returning a MeshPayload. MeshPayloadBuilder is a Protocol
    (not @runtime_checkable), so this asserts by invocation.
    """
    builder = RawPdfPayloadBuilder()
    assert callable(getattr(builder, "build", None))
    result = builder.build(pdf_bytes=b"%PDF-1.7 test")
    assert isinstance(result, MeshPayload)


# ---------------------------------------------------------------------------
# Behaviour
# ---------------------------------------------------------------------------


def test_raw_pdf_builder_passes_bytes_through_unchanged():
    """
    The raw builder must transmit the PDF bytes exactly as generated —
    byte-identical, no wrapping, no re-encoding.
    """
    pdf_bytes = b"%PDF-1.7\n...binary content...\n%%EOF"
    payload = RawPdfPayloadBuilder().build(pdf_bytes=pdf_bytes)
    assert payload.payload_bytes == pdf_bytes


def test_raw_pdf_builder_sets_pdf_content_type():
    payload = RawPdfPayloadBuilder().build(pdf_bytes=b"%PDF-1.7")
    assert payload.content_type == "application/pdf"


def test_raw_pdf_builder_handles_empty_bytes():
    """
    Degenerate input must not raise here. An empty PDF is a bug upstream
    (the PDF worker), but the builder is a pure passthrough and must not
    add its own validation layer that could mask where the bug lives.
    """
    payload = RawPdfPayloadBuilder().build(pdf_bytes=b"")
    assert payload.payload_bytes == b""
    assert payload.content_type == "application/pdf"


# ---------------------------------------------------------------------------
# MeshPayload dataclass contract
# ---------------------------------------------------------------------------


def test_mesh_payload_is_frozen():
    """
    MeshPayload is frozen so a builder result cannot be mutated between
    construction and send — the payload handed to MeshClient is exactly
    the payload the builder produced.
    """
    payload = MeshPayload(payload_bytes=b"x", content_type="application/pdf")
    with pytest.raises(dataclasses.FrozenInstanceError):
        payload.payload_bytes = b"y"  # type: ignore[misc]

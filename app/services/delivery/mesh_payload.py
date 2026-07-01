"""
MESH payload construction seam.

Defines the MeshPayloadBuilder Protocol and the RawPdfPayloadBuilder
implementation. The dispatcher (mesh_worker.py) builds its outbound MESH
payload exclusively through this seam, keeping the dispatcher
payload-agnostic: queue handling, retry, fallback, and tracking are
unchanged whichever builder is wired at startup.

PROVISIONAL STATUS: RawPdfPayloadBuilder is the only implementation in this
phase and it is provisional. There is no registered, non-deprecated MESH
workflow ID for raw PDF delivery to a GP practice's clinical system (see
docs/nhs_integration_reference.md, "Workflow IDs"); raw PDF is viable in
production only under a locally agreed workflow arrangement with the
receiving practice. The likely production endgame is GP Connect Send
Document, whose GpConnectSendDocumentPayloadBuilder is a separate ticket
(ticket_gpconnect_payload_builder.md) and would produce an ITK3-conformant
FHIR Message with content type application/fhir+json.

Workflow ID coupling note (for the GP Connect ticket): the MESH workflow ID
is env-driven (MESH_WORKFLOW_ID, read by mesh_worker_main.py) and is NOT a
builder concern in this phase. In the GP Connect specifications the workflow
ID and payload format are coupled (e.g. GPCONNECT_SEND_DOCUMENT implies an
ITK3 payload), so when a second builder is added, the builder/workflow-ID
pairing must be validated at startup rather than left as two independently
settable values.

Architecture rules:
- This module performs no I/O: no database, no network, no filesystem.
- This module must never import clinical engine modules, routers,
  repositories, or the MESH client.
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class MeshPayload:
    """
    The bytes and content type handed to MeshClient.send_message.

    payload_bytes -- the exact message body to POST to MESH.
    content_type  -- the Content-Type header value for the send.
    """

    payload_bytes: bytes
    content_type: str


class MeshPayloadBuilder(Protocol):
    """
    Structural interface for MESH payload construction.

    Implementations receive the generated PDF bytes for a submission and
    return the MeshPayload to transmit. Implementations must be pure
    functions of their inputs (no I/O), so the dispatcher's crash-safety
    reasoning is unaffected by builder choice.
    """

    def build(self, *, pdf_bytes: bytes) -> MeshPayload: ...


class RawPdfPayloadBuilder:
    """
    Provisional builder: the PDF bytes are the MESH message body, unchanged,
    with content type application/pdf. See the module docstring for the
    conditions under which this is production-viable.
    """

    def build(self, *, pdf_bytes: bytes) -> MeshPayload:
        return MeshPayload(
            payload_bytes=pdf_bytes,
            content_type="application/pdf",
        )

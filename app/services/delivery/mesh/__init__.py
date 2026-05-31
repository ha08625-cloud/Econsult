"""MESH delivery client package (Phase 2a).

A pure client library for the NHS MESH API: mutual-TLS HTTP transport, HMAC
auth-header construction, and the message send / track / handshake calls. No
database, no worker loop, no wiring -- those arrive in later phases of the MESH
integration plan.

Import surface::

    from app.services.delivery.mesh import (
        MeshClient,
        MeshError,
        MeshTransientError,
        MeshTerminalError,
    )
"""

from app.services.delivery.mesh.client import MeshClient
from app.services.delivery.mesh.errors import (
    MeshError,
    MeshTerminalError,
    MeshTransientError,
)

__all__ = [
    "MeshClient",
    "MeshError",
    "MeshTerminalError",
    "MeshTransientError",
]
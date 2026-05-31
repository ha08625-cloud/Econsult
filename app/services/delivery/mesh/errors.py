"""
MESH client exception hierarchy.

The MESH dispatcher (Phase 3) branches on the exception *type* to decide
retry-versus-fallback:

  - ``MeshTransientError`` -- retryable. Network/transport failures, 5xx
    responses, and authentication/clock failures (which the MESH API reports
    as a 403 with an empty ``errorCode``) fall here. The dispatcher retries
    with backoff up to ``MAX_MESH_ATTEMPTS``, then falls back to email.
  - ``MeshTerminalError`` -- not retryable. Business errors (a 4xx with a
    populated ``errorCode``, e.g. an unregistered recipient), any other 4xx,
    and malformed/unparseable responses fall here. The dispatcher abandons
    MESH and falls back to email immediately.

Both derive from ``MeshError`` so a caller that does not care about the
distinction can catch the whole family with a single ``except`` clause.

The transient/terminal split mirrors the MESH error semantics recorded in
``docs/nhs_integration_reference.md`` ("Error behaviour"): authentication
failures leave ``errorCode`` empty and are retryable; business errors populate
``errorCode`` and are permanent.

Phase 2a deliberately keeps these classes attribute-free. The classification
helper raises them with a human-readable message that includes the HTTP status
and any MESH ``errorCode``. If a later phase needs the error code as a
structured attribute (to populate ``mesh_jobs.last_error_code`` without parsing
the message), that is a small additive change to make then, alongside the
dispatcher that consumes it.
"""


class MeshError(Exception):
    """Base class for all MESH client errors."""


class MeshTransientError(MeshError):
    """A retryable MESH failure (transport, 5xx, or auth/clock failure)."""


class MeshTerminalError(MeshError):
    """A non-retryable MESH failure (business error or malformed response)."""
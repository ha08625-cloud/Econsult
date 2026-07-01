"""
MESH dispatcher retry constants.

Defines the backoff schedule and maximum attempt count for MESH send retry,
plus the bounded startup-handshake retry schedule. This module has no imports
from any other application module.

MAX_MESH_ATTEMPTS is derived from the schedule length. It represents the
total number of MESH send attempts (first attempt plus all retries). This is
the single canonical expression of the exhaustion threshold. No other module
may define its own maximum. The threshold is the dispatcher's concern, not
the repository's — MeshRepository.mark_failed records attempts and returns
the count; the dispatcher compares against MAX_MESH_ATTEMPTS and decides
whether to retry or fall back to email.

The MESH backoff window (~21 minutes) is deliberately shorter than the email
path's (~71 minutes, see delivery_constants.py): a working fallback channel
(Mailgun) exists, so prolonged MESH retries only delay the practice
receiving the form. On exhaustion the dispatcher falls back to email rather
than parking the job.

HANDSHAKE_RETRY_DELAYS_SECONDS bounds the in-process retry of the startup
handshake on MeshTransientError (total patience ~8.5 minutes). The bound is
deliberate: the MESH error classification maps a 403 with an EMPTY errorCode
(auth/clock skew) to MeshTransientError, so bad credentials can present as
transient. An unbounded retry would mask a credential error forever; with
the bound, a genuine Spine blip is absorbed in-process while persistent
failure still aborts per the Fail-Fast Configuration invariant (the process
exits and Railway's restart loop surfaces the problem).
MeshTerminalError at handshake aborts immediately with no retry.
"""

MESH_RETRY_BACKOFF_MINUTES: list[int] = [1, 5, 15]

MAX_MESH_ATTEMPTS: int = len(MESH_RETRY_BACKOFF_MINUTES) + 1  # 4

HANDSHAKE_RETRY_DELAYS_SECONDS: list[int] = [10, 30, 60, 120, 300]

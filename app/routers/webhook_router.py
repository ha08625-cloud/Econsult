"""
Webhook router.

Handles inbound delivery event signals from Mailgun. This router is the only
public endpoint that receives external provider callbacks.

Security model:
1. Timestamp check: webhooks older than 15 minutes are silently dropped
   (return 200 OK to prevent Mailgun from retrying a permanently stale signal).

2. HMAC verification: the signature in the payload is verified against
   MAILGUN_SIGNING_KEY using HMAC-SHA256 over (timestamp + token). Requests
   that fail verification return 403. The key is read from app.state at
   startup; startup validation ensures it is present when MAILGUN_API_KEY
   is set.

3. Replay protection: each webhook carries a unique token. The router
   attempts INSERT INTO webhook_tokens ... ON CONFLICT DO NOTHING. If no row
   is inserted, the token was already seen — the request is a replay and
   returns 200 OK silently (a 2xx stops Mailgun retrying). Expired tokens
   (older than 15 minutes) are deleted at the start of each request to keep
   the table bounded without a cron job.

Race condition handling:
If a webhook arrives before the delivery worker has committed the
provider_message_id to delivery_jobs, the lookup returns None. The router
returns 406 Not Acceptable, which causes Mailgun to retry with exponential
backoff. This leverages the provider's own retry logic rather than holding
open a synchronous connection.

Status transitions triggered here:
  'delivered' event  -> delivery_jobs.status = 'delivered'
  'failed' event     -> delivery_jobs.status = 'failed'
  'dropped' event    -> delivery_jobs.status = 'failed'
  all other events   -> no status change; payload appended to provider_events

All transitions append the raw payload to the provider_events JSONB column
for a lossless audit trail.

Architecture rules:
- This router must never import clinical engine modules.
- This router must never generate PDFs or send emails.
- Signature verification uses hmac.compare_digest to prevent timing attacks.
- The signing key is never logged.
"""

import hashlib
import hmac
import logging
import time

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from app.repositories.delivery_repository import DeliveryRepository
from app.core.db import get_conn

logger = logging.getLogger(__name__)

router = APIRouter(tags=["webhooks"])

_TIMESTAMP_TOLERANCE_SECONDS = 900  # 15 minutes


def _verify_mailgun_signature(signing_key: str, token: str, timestamp: str, signature: str) -> bool:
    """
    Verify a Mailgun webhook HMAC-SHA256 signature.

    Mailgun signs the concatenation of timestamp + token with the signing key.
    Uses hmac.compare_digest to prevent timing attacks.

    Returns True if the signature is valid, False otherwise.
    """
    expected = hmac.new(
        key=signing_key.encode("utf-8"),
        msg=f"{timestamp}{token}".encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def _is_stale(timestamp_str: str) -> bool:
    """
    Return True if the webhook timestamp is older than the tolerance window.

    Stale webhooks are silently accepted (200 OK) to prevent Mailgun from
    retrying a signal that can no longer be useful.
    """
    try:
        ts = int(timestamp_str)
    except (ValueError, TypeError):
        return True
    return abs(time.time() - ts) > _TIMESTAMP_TOLERANCE_SECONDS


def _consume_token(database_url: str, token: str) -> bool:
    """
    Attempt to record a webhook token for replay protection.

    Deletes expired tokens first to keep the table bounded, then inserts
    the new token. Returns True if the token is fresh (insert succeeded),
    False if it was already seen (ON CONFLICT fired, no row inserted).
    """
    with get_conn(database_url) as conn:
        with conn.cursor() as cur:
            # Purge tokens older than the tolerance window first.
            cur.execute(
                """
                DELETE FROM webhook_tokens
                WHERE received_at < NOW() - INTERVAL '15 minutes'
                """
            )

            cur.execute(
                """
                INSERT INTO webhook_tokens (token)
                VALUES (%s)
                ON CONFLICT (token) DO NOTHING
                """,
                (token,),
            )
            return cur.rowcount == 1


@router.post("/webhooks/mailgun")
async def mailgun_webhook(request: Request) -> Response:
    """
    Receive and process a Mailgun delivery event webhook.

    Mailgun sends form-encoded payloads. The three security fields
    (timestamp, token, signature) are always present on valid requests.
    The event-data fields vary by event type.

    Returns:
        200 OK  — signal processed, or silently dropped (stale / replay)
        403     — HMAC signature invalid
        406     — provider_message_id not yet committed (race condition; Mailgun retries)
    """
    form = await request.form()
    payload = dict(form)

    # Extract security fields.
    timestamp = payload.get("timestamp", "")
    token = payload.get("token", "")
    signature = payload.get("signature", "")
    event_type = payload.get("event-data[event]") or payload.get("event", "")
    provider_message_id = (
        payload.get("event-data[message][headers][message-id]")
        or payload.get("message-id", "")
    ).strip("<>")

    # 1. Timestamp check — drop stale signals silently.
    if _is_stale(timestamp):
        logger.warning(
            "Webhook: stale timestamp dropped event=%s provider_message_id=%s",
            event_type,
            provider_message_id,
        )
        return JSONResponse(status_code=200, content={"status": "ok"})

    # 2. HMAC verification.
    signing_key = getattr(request.app.state, "mailgun_signing_key", None)
    if not signing_key:
        # Startup validation ensures this is set in production. If it is
        # somehow absent at request time, refuse rather than skip verification.
        logger.error("Webhook: MAILGUN_SIGNING_KEY not available in app.state")
        return JSONResponse(status_code=403, content={"error": "misconfigured"})

    if not _verify_mailgun_signature(signing_key, token, timestamp, signature):
        logger.warning(
            "Webhook: HMAC verification failed event=%s", event_type
        )
        return JSONResponse(status_code=403, content={"error": "invalid signature"})

    # 3. Replay protection.
    database_url: str = request.app.state.database_url
    is_fresh = _consume_token(database_url, token)
    if not is_fresh:
        logger.info(
            "Webhook: replay token rejected event=%s provider_message_id=%s",
            event_type,
            provider_message_id,
        )
        return JSONResponse(status_code=200, content={"status": "ok"})

    # All security checks passed. Process the event.
    delivery_repo: DeliveryRepository = request.app.state.delivery_repo

    logger.info(
        "Webhook: processing event=%s provider_message_id=%s",
        event_type,
        provider_message_id,
    )

    if event_type == "delivered":
        found = delivery_repo.mark_delivered(provider_message_id)
        if not found:
            logger.warning(
                "Webhook: provider_message_id not found (race condition) "
                "event=%s provider_message_id=%s — returning 406",
                event_type,
                provider_message_id,
            )
            return JSONResponse(status_code=406, content={"error": "not ready"})

        delivery_repo.append_provider_event(provider_message_id, payload)
        logger.info(
            "Webhook: delivery confirmed provider_message_id=%s", provider_message_id
        )

    elif event_type in ("failed", "dropped"):
        found = delivery_repo.mark_provider_failed(provider_message_id)
        if not found:
            logger.warning(
                "Webhook: provider_message_id not found (race condition) "
                "event=%s provider_message_id=%s — returning 406",
                event_type,
                provider_message_id,
            )
            return JSONResponse(status_code=406, content={"error": "not ready"})

        delivery_repo.append_provider_event(provider_message_id, payload)
        logger.info(
            "Webhook: permanent provider failure recorded event=%s "
            "provider_message_id=%s",
            event_type,
            provider_message_id,
        )

    else:
        # Unknown or informational event (e.g. 'opened', 'clicked').
        # Append to audit log but do not change status.
        delivery_repo.append_provider_event(provider_message_id, payload)
        logger.info(
            "Webhook: informational event appended event=%s "
            "provider_message_id=%s",
            event_type,
            provider_message_id,
        )

    return JSONResponse(status_code=200, content={"status": "ok"})
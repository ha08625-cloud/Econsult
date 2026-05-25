# NHS Integration Reference

A reference document capturing **observed facts** about NHS Digital APIs and
services we integrate with. This document is intentionally not an
architecture spoke — it does not describe how *we* use these systems. It
describes how *they* behave, based on direct investigation against official
sandboxes and integration environments.

The purpose is to ensure that hard-won protocol-level knowledge from
sandbox sessions outlives the planning documents that triggered the
investigation. When implementing or maintaining NHS integrations, read this
first to avoid re-running discovery work.

## How to use this document

- Each section covers one integration (MESH, PDS, NHS login, etc.).
- Sections follow a consistent template: **Endpoint inventory**, **Auth model**, **Request/response shapes**, **State machine**, **Error behaviour**, **Known gotchas**.
- Facts are tagged with their provenance: `[sandbox v1.0.54]` for the local mesh-sandbox, `[NHS docs]` for documented behaviour we haven't independently verified, `[PTL]` for facts verified against the NHS Path To Live integration environment.
- When a fact is observed to change between sandbox versions or environments, both facts are kept and tagged with their respective environments. Do not delete observed facts even if they appear superseded — they may resurface as bugs in production.

## Document contents

- [MESH (Message Exchange for Social Care and Health)](#mesh)
- [PDS (Personal Demographics Service)](#pds) — placeholder, not yet investigated
- [NHS login](#nhs-login) — placeholder, scope not yet confirmed

---

## MESH

The Message Exchange for Social Care and Health. Used for transferring
clinical documents between NHS organisations. Our system uses MESH to
deliver eConsult referrals to GP practices.

### Operational tier

`[NHS docs]` MESH is a **silver service**: operational 24/7/365, but only
supported by NHS Digital staff during business hours (Mon-Fri 08:00-18:00,
excluding bank holidays).

### Endpoint inventory

All paths are relative to the MESH base URL for the environment:
- `[NHS docs]` sandbox (local): `https://localhost:8700`
- `[NHS docs]` integration (PTL): `https://msg.int.spine2.ncrs.nhs.uk`
- `[NHS docs]` production: `https://mesh-sync.national.ncrs.nhs.uk`

| Path | Method | Purpose |
|---|---|---|
| `/messageexchange/<mailbox_id>` | POST | Handshake (also returns mailbox identity confirmation) |
| `/messageexchange/<mailbox_id>/outbox` | POST | Send a message |
| `/messageexchange/<mailbox_id>/outbox/tracking?messageID=<id>` | GET | Get delivery status of a sent message |
| `/messageexchange/<mailbox_id>/inbox` | GET | List messages in this mailbox's inbox (returns `{"messages": [...]}`) |
| `/messageexchange/<mailbox_id>/inbox/<message_id>` | GET | Download the bytes of a received message |
| `/messageexchange/<mailbox_id>/inbox/<message_id>/status/acknowledged` | PUT | Acknowledge receipt of a message (recipient action) |
| `/health` | GET | Health check (unauthenticated) |

`[sandbox v1.0.54]` The following paths do **not** exist or are not
supported:

- `GET /messageexchange/<mailbox_id>/outbox` — returns `Method Not Allowed`. There is no outbox listing endpoint.
- `GET /messageexchange/<mailbox_id>/outbox/tracking/<message_id>` (path-style) — returns 404. Tracking is query-string only.

### Auth model

`[sandbox v1.0.54]` The MESH API uses a custom HMAC-based authorization
scheme:

```
Authorization: NHSMESH <mailbox_id>:<nonce>:<nonce_count>:<timestamp>:<hmac>
```

- `mailbox_id` — the calling mailbox
- `nonce` — fresh UUID per request (any v4 UUID is accepted)
- `nonce_count` — `1` in our usage; the field exists for replay-attack prevention schemes but the sandbox does not enforce sequence increments
- `timestamp` — UTC, formatted `YYYYMMDDHHmm` (**minute granularity, no seconds**)
- `hmac` — hexadecimal HMAC-SHA256 of `<mailbox_id>:<nonce>:<nonce_count>:<password>:<timestamp>`, signed with the shared key

The HMAC input includes the mailbox password and timestamp; the shared key
is the HMAC secret.

`[sandbox v1.0.54]` **Auth headers must be regenerated per request**
because of the one-minute timestamp granularity. Caching the header risks
sending requests with a stale timestamp that may be rejected by the time
the request arrives.

### Health check

`[sandbox v1.0.54]` Unauthenticated `GET /health` returns:

```json
{"env": "local", "build_label": "latest", "status": "running", "outcome": "Yes"}
```

The `outcome: "Yes"` field is the canonical signal of health. Production
MESH presumably uses different `env` and `build_label` values; we have not
yet verified the production response shape.

### Handshake

`[sandbox v1.0.54]` `POST /messageexchange/<mailbox_id>` with valid auth
and no body returns:

- Status: `200 OK`
- Body: `{"mailboxId": "<mailbox_id>"}`

This is the recommended startup check before sending any messages.
A failed handshake catches credential misconfiguration immediately.

### Sending a message

`[sandbox v1.0.54]` Request:

```
POST /messageexchange/<mailbox_id>/outbox
Authorization: NHSMESH ...
Mex-From: <sender_mailbox_id>
Mex-To: <recipient_mailbox_id>
Mex-WorkflowID: <workflow_id>
Mex-LocalID: <our_correlation_id>          # optional but recommended
Mex-ClientVersion: <version>               # optional
Mex-OSName: <name>                         # optional
Mex-OSVersion: <version>                   # optional
Content-Type: <mime type>

<binary or JSON body>
```

Successful response:

- Status: **`202 Accepted`** (not `200 OK`)
- Body: `{"messageID": "<32-character uppercase hexadecimal string>"}`

Example messageID: `093D3376E61747D7BC1E077C8E5F1043`

`[sandbox v1.0.54]` **Important**: the messageID format is 32 uppercase
hex characters, **not a standard hyphenated UUID**. Storage type should be
`TEXT`, not `UUID`. The format does not match Python's `uuid.UUID()`
parser.

`[sandbox v1.0.54]` `Mex-LocalID` is accepted but **not** echoed in the
send response body. It is persisted by Spine and exposed via the tracking
endpoint (see below).

### Message lifecycle / tracking

`[sandbox v1.0.54]` After sending, the message progresses through states
observable via the tracking endpoint
`GET /outbox/tracking?messageID=<id>`. Tracking returns a verbose JSON
object; the load-bearing fields are:

| Field | Meaning |
|---|---|
| `messageId` | The 32-hex-char Spine ID |
| `localId` | The `Mex-LocalID` we sent (empty string if we didn't send one) |
| `status` | Current state — see state table below |
| `statusSuccess` | `SUCCESS` or `ERROR` (orthogonal to status) |
| `recipient` | Recipient mailbox |
| `recipientOdsCode` | Recipient ODS |
| `sender` | Sender mailbox |
| `senderOdsCode` | Sender ODS |
| `uploadTimestamp` | When we POSTed |
| `downloadTimestamp` | When recipient downloaded the bytes (empty until then) |
| `expiryTime` | When the message will be deleted from Spine if not acknowledged |
| `workflowId` | The workflow ID we sent |
| `fileSize` | Bytes |
| `chunkCount` | Number of chunks (>1 for chunked uploads, untested) |

State machine (observed):

| `status` | `statusSuccess` | `downloadTimestamp` | What this means |
|---|---|---|---|
| `Accepted` | `SUCCESS` | empty | Spine has the message; recipient hasn't fetched it yet |
| `Accepted` | `SUCCESS` | populated | Recipient downloaded the bytes but hasn't acknowledged |
| `Acknowledged` | `SUCCESS` | populated | Recipient confirmed receipt and processing |
| `Accepted` or `Acknowledged` | `ERROR` | varies | Recipient rejected the message (untested in sandbox; behaviour inferred from MESH spec) |

`[sandbox v1.0.54]` **Important**: downloading a message does *not*
transition status. The recipient must explicitly acknowledge via
`PUT /inbox/<id>/status/acknowledged` for status to become `Acknowledged`.
`downloadTimestamp` is independent of status.

`[sandbox v1.0.54]` The sandbox does **not** automatically generate
acknowledgement on download. We had to explicitly PUT the acknowledgement
endpoint to observe the status transition.

### Acknowledging a received message

`[sandbox v1.0.54]` The recipient acknowledges via:

```
PUT /messageexchange/<mailbox_id>/inbox/<message_id>/status/acknowledged
Authorization: NHSMESH ...
```

Response:
- Status: `200 OK`
- Body: `{"messageId": "<message_id>"}`

In our system this is performed by the GP practice's MESH client, not by
us. We only consume the resulting status transition via the tracking
endpoint.

### Error behaviour

`[sandbox v1.0.54]` Error responses follow a consistent JSON shape:

```json
{"errorEvent": "<category>", "errorCode": "<code>", "errorDescription": "<human readable>"}
```

| Error class | Status | `errorEvent` | `errorCode` | `errorDescription` |
|---|---|---|---|---|
| Auth failure (bad signature) | 403 | empty | empty | "Invalid Authentication Token" |
| Auth failure (no header) | 403 | empty | empty | "Error reading from Authorization header" |
| Recipient mailbox unknown | 417 | "SEND" | "12" | "Unregistered to address" |
| MessageID not found in tracking | 404 | empty | empty | "Not Found" |

`[sandbox v1.0.54]` **Important**: business errors populate `errorCode` and
`errorEvent`. Authentication errors leave them empty. This is the basis
for differentiating permanent business errors (should not retry) from
transient auth failures (should refresh credentials and retry).

`[sandbox v1.0.54]` Note that 4xx for "unregistered recipient" is
`417 Expectation Failed`, not `400 Bad Request` or `404 Not Found`. This
is unusual but well-defined.

### Idempotency and duplicate sends

`[sandbox v1.0.54]` **MESH does not deduplicate based on `Mex-LocalID`.**
If the same payload is POSTed twice with the same `Mex-LocalID`, Spine
assigns **two different** messageIDs and the recipient receives **two
messages**. The `Mex-LocalID` field is purely diagnostic — it persists in
the tracking record so an operator can identify which of our submissions
generated which Spine messageID, but it does not prevent duplicate
delivery.

This means: a network timeout after Spine has accepted the POST but
before our HTTP client receives the response will cause a duplicate send
on retry. Production code must accept this risk.

`[sandbox v1.0.54]` There is no outbox listing endpoint, so we cannot
enumerate all messages we've sent that share a `Mex-LocalID`. This
limits the recovery mechanisms available after a dispatcher crash.

### Known sandbox limitations vs production

`[sandbox v1.0.54]`

- The sandbox uses a self-signed TLS certificate. Production uses valid certificates.
- The sandbox's auth implementation is permissive on `nonce_count`; production may enforce monotonic increments per nonce.
- The sandbox runs over HTTPS on port 8700 (mapped from container port 443). Production uses standard 443.
- The sandbox does not appear to enforce message size limits (we did not test the upper bound).
- The sandbox auto-delivers messages to the target mailbox without any onboarding handshake. Production requires the target ODS code to be registered.
- The sandbox does not generate failure-receipt scenarios automatically; we have not observed a `statusSuccess: "ERROR"` response yet.

### MIME types

`[sandbox v1.0.54]` The sandbox accepts arbitrary `Content-Type` headers.
We have tested:

- `application/octet-stream` — works
- `application/fhir+json` — expected to work for our actual use case but not yet sandbox-tested

`[NHS docs]` Production MESH for ITK3 FHIR transfer requires
`application/fhir+json`. The `Mex-WorkflowID` is what actually drives
processing on the recipient side, not the MIME type, but the MIME type
should be correct for downstream consumers.

### Workflow IDs

`[NHS docs]` `Mex-WorkflowID` is a free-text string in the protocol but
must be a registered, agreed-with-recipient workflow ID in production. For
ITK3 document transfer it identifies the message as containing a FHIR
ITK3 Bundle.

The sandbox accepts any string. We used `TEST_WORKFLOW` during
investigation. Production value is `pending` and must be obtained from
NHS Digital before go-live.

### Useful undocumented observations

`[sandbox v1.0.54]`

- The sandbox returns HTTP/1.1, not HTTP/2 (ALPN negotiation declines h2).
- The sandbox's response headers include `server: uvicorn`, indicating it's a Python ASGI service. Behaviour likely differs from production Spine which runs on different infrastructure.
- The `dtsId` field in tracking records appears to be a duplicate of `messageId` in the sandbox. Production may differentiate these.
- Tracking records persist after acknowledgement; we have not tested whether they expire.

---

## PDS

**Not yet investigated.** This section will be populated when we run the
PDS sandbox investigation as a precursor to Phase 1b implementation.

### Open questions to investigate

- Auth model: PDS FHIR uses application-restricted OAuth2 with signed JWT, materially different from MESH. Need to verify the JWT signing flow against the sandbox.
- Response shape for `verified` cases (full FHIR Patient resource).
- Response shape for `not_found` (404 with FHIR OperationOutcome? Plain 404?).
- Response shape for demographic `mismatch` (does PDS distinguish "found but doesn't match" from "verified match"? Or is mismatch a client-side comparison we must do ourselves?).
- 5xx and timeout behaviour.
- Rate limits.
- The PDS sandbox is documented as stateless with hard-coded responses. The set of available test patients needs cataloguing.

### Operational tier

`[NHS docs]` PDS FHIR API is a **silver service**: 24/7 operational, business-hours support only.

---

## NHS login

**Scope not yet confirmed.** Patient-facing authentication via NHS login
has been raised as a possible future requirement but is not part of the
current implementation plan. This section is a placeholder.

If/when NHS login is added to the system, the investigation should cover:

- Sandpit vs Integration environment differences (sandpit is not PDS-connected; full identity verification requires Integration).
- OIDC client registration process and timing (sandpit requests are processed within 24 hours per NHS docs).
- Available test accounts and their pre-configured identity verification states.
- Scope set: which `profile_*` scopes our use case requires.
- Token lifetime and refresh behaviour.

---

## Document maintenance

When adding a new section:

1. Follow the same template as the MESH section above.
2. Tag every fact with its provenance.
3. Do not duplicate design decisions from architecture documents — this is a reference of *their* behaviour, not *ours*.
4. When sandbox findings later differ from PTL or production findings, **keep both** and tag them clearly. Do not delete superseded facts.
5. Update the document contents list at the top.

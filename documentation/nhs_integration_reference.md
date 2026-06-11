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
- [PDS (Personal Demographics Service)](#pds)
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
- The sandbox does not enforce mTLS. The container's uvicorn process is launched as `uvicorn mesh_sandbox.api:app --host 0.0.0.0 --port 443 --workers 1 --ssl-certfile /tmp/server-cert.pem --ssl-keyfile /tmp/server-cert.key` — no `--ssl-ca-certs` flag and no `--ssl-cert-reqs` flag. The image exposes no environment variable that would toggle these on (the only TLS/auth-adjacent env vars in the running container are `SSL=yes`, `AUTH_MODE=full`, `STORE_MODE=file`, and `SHARED_KEY`). The server presents its own certificate but never asks the client to present one. Production MESH requires mTLS with a client certificate signed by an NHS-issued CA. Local mTLS parity must therefore be achieved by an external mechanism (we use an nginx TLS-terminating proxy in front of the sandbox — see `sandbox/docker-compose.yml`); the sandbox itself cannot be configured to demand a client cert.
- The sandbox's server certificate paths inside the container are `/tmp/server-cert.pem` and `/tmp/server-cert.key`. The cert is generated by the container's entrypoint at startup; we do not control the CA, and the cert will differ across container restarts unless we mount our own over those paths.
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

`[NHS docs]` `Mex-WorkflowID` is a free-text field at the protocol level but
must be a registered, agreed-with-recipient value in production. A MESH
mailbox must be explicitly configured to send or receive each workflow ID
(rules of the form "Mailbox X is allowed to Send/Receive messages with
workflow ID Y"). Messages sent with a workflow ID the recipient mailbox is
not configured for are rejected with a 417 (unregistered recipient).

`[NHS docs]` NHS England publishes an official spreadsheet of all registered
workflow groups and IDs. The version reviewed here is dated May 2026. Each
workflow group is a named use case; each group contains one or more
initiator IDs (sender) and, where acknowledgement is expected, responder
IDs (receiver, conventionally suffixed `_ACK`).

#### GP Federation group (group 77)

This is the group covering consultation reports sent to GP practices.
Relevant IDs:

| Workflow ID | Spec version | Purpose |
|---|---|---|
| `GPFED_CONSULT_REPORT` | GP Connect Send Document v1.x | Consultation report — ITK3/FHIR payload required |
| `GPFED_CONSULT_REPORT_ACK` | v1.x | Acknowledgement of the above |
| `GPCONNECT_SEND_DOCUMENT` | GP Connect Send Document v2.x | Document send (incl. consultation report) — ITK3/FHIR payload required |
| `GPCONNECT_SEND_DOCUMENT_ACK` | v2.x | Acknowledgement of the above |

The group also contains `GPCONNECT_UPDATE_RECORD` (pharmacy update to GP
record), which is unrelated to consultation reports.

`[NHS docs]` The two consultation-report initiator IDs are the same
capability at different spec versions, not different payload formats:

- GP Connect Send Document v1.x uses `GPFED_CONSULT_REPORT`.
- GP Connect Send Document v2.x (public beta) renamed the workflow IDs:
  all documents use `GPCONNECT_SEND_DOCUMENT`, and
  `GPFED_CONSULT_REPORT_ACK` was changed to `GPCONNECT_SEND_DOCUMENT_ACK`.
  Senders that have not updated to v2.0.0 continue to use the old IDs.
- Both versions require the message to be a FHIR Message constructed to
  the ITK3 standard, delivered over MESH. There is no version of GP
  Connect Send Document that accepts a raw (non-FHIR) document payload.
- The v2 spec states the NHS is aiming to deprecate the
  `GPFED_CONSULT_REPORT*` workflow IDs (stated target: 2024). The May 2026
  registered-workflows spreadsheet nonetheless still lists them outside the
  deprecated group. Both facts are kept per this document's conventions:
  the v1 IDs remain in active use for backwards compatibility, but new
  integrations should target the v2 IDs.
- Receiving solutions are required to support backwards compatibility for
  GP Connect Send Document v1.3.1/v1.3.2, i.e. a consultation summary may
  arrive at a practice under either workflow ID, and practices currently
  need to support both.

`[NHS docs]` The v1 spec note on scope: the only use case for messages sent
with a `GPFED_CONSULT_REPORT*` workflow ID is a summary of a consultation
that took place outside the citizen's regular GP practice. Under the v2 ID,
the payload could be any document type (including a consultation summary);
v2 distinguishes document types by SNOMED code rather than by workflow ID.

#### No registered workflow ID for raw PDF delivery

`[NHS docs]` The registered-workflows spreadsheet contains no active,
non-deprecated workflow ID for delivering a raw (non-ITK3) PDF to a GP
practice's clinical system. `DISCH_KET` (Discharge Kettering XML) was the
pre-GP-Connect document-delivery route; it appears in the "Deprecated
WorkflowIDs" group in the May 2026 spreadsheet and must not be used for new
integrations. Raw binary delivery over MESH remains possible at the
transport level, but only under a locally agreed workflow ID that the
recipient mailbox has been explicitly configured for — i.e. a bespoke
arrangement with the receiving practice, outside any published NHS
specification. How (or whether) the practice's clinical system (EMIS,
SystmOne) surfaces such a message to clinical staff is determined by the
practice's local MESH client configuration and is not publicly documented.
Reports exist in NHS developer community forums of raw PDFs arriving in a
practice's MESH mailbox without becoming visible to the GP — transport
success without clinical-system processing. Transport-level
acknowledgement (the MESH tracking endpoint reporting "Acknowledged") is
therefore not evidence that a document was processed or seen at the
clinical layer.

#### GP Connect Send Document addressing is patient-based

`[NHS docs]` Under GP Connect Send Document, the `Mex-To` header is not a
plain destination mailbox ID. It is populated via the MESH endpoint lookup
convention:

```
GPPROVIDER_<NhsNumber>_<DateOfBirth>_<Surname>
```

with `_` as the delimiter and date of birth in `YYYYMMDD` format. The
message is routed to the patient's registered practice. A spec-conformant
GP Connect Send Document integration therefore requires the patient's NHS
number, date of birth, and surname at send time. (The MESH Client
equivalent populates `To_DTS` in the `.ctl` file with the same pattern.)

`[unverified — industry practice]` Patient-facing online consultation
products generally do not require patients to enter their NHS number;
suppliers obtain it server-side by tracing via a PDS demographics search
(name, date of birth, postcode) after submission. Adopting GP Connect Send
Document without mandating NHS number entry would therefore imply a PDS
trace step. Not independently verified against any supplier's
documentation.

#### Endpoint lookup service

`[NHS docs]` NHS provides an endpoint lookup API that can verify whether a
specific practice's MESH mailbox is configured to receive messages with a
given workflow ID:

```
GET https://mesh-sync.spineservices.nhs.uk/messageexchange/endpointlookup/<ODS_code>/<workflow_id>
```

This requires both the ODS code and the workflow ID as inputs. It is a
verification tool, not a discovery tool: it cannot enumerate the workflow
IDs a mailbox supports without a candidate value to test against. If the
lookup returns a mailbox, the practice is configured to receive that
message type. If it returns nothing, the workflow ID is not configured on
that mailbox and the practice's IT team must be contacted.

`[NHS docs]` GP practices are an exception to the usual rule of one
workflow group per mailbox. Most GP practice mailboxes are configured for
multiple workflow groups. It is therefore likely (though not guaranteed)
that a practice receiving electronic consultation reports has
`GPFED_CONSULT_REPORT` (and/or `GPCONNECT_SEND_DOCUMENT`) configured. This
should be verified via the endpoint lookup before the first production
send to any new practice.

#### Sandbox behaviour

`[sandbox v1.0.54]` The sandbox accepts any string as `Mex-WorkflowID` and
performs no validation. `TEST_WORKFLOW` was used during initial
investigation. Subsequent testing should use whichever workflow ID is
agreed for production (undecided at the time of writing — depends on
whether the first practice accepts a locally agreed raw-document workflow
ID or requires GP Connect Send Document) so that `.env.sandbox` mirrors
production conditions.

### Useful undocumented observations

`[sandbox v1.0.54]`

- The sandbox returns HTTP/1.1, not HTTP/2 (ALPN negotiation declines h2).
- The sandbox's response headers include `server: uvicorn`, indicating it's a Python ASGI service. Behaviour likely differs from production Spine which runs on different infrastructure.
- The `dtsId` field in tracking records appears to be a duplicate of `messageId` in the sandbox. Production may differentiate these.
- Tracking records persist after acknowledgement; we have not tested whether they expire.

---

## PDS

The Personal Demographics Service. The national database of NHS patient
demographic details. Our system uses PDS to look up a patient's currently
registered GP practice (via ODS code) so we can deliver electronic
referrals to the right destination.

This section covers the **FHIR R4** version of the PDS API. The older
HL7 V3 version is documented as deprecated and not used here.

### Operational tier

`[NHS docs]` PDS FHIR API is a **silver service**: 24/7 operational,
business-hours support only.

### Endpoint inventory

All paths are relative to the PDS base URL for the environment:
- `[sandbox]` sandbox: `https://sandbox.api.service.nhs.uk/personal-demographics/FHIR/R4`
- `[NHS docs]` integration (PTL): `https://int.api.service.nhs.uk/personal-demographics/FHIR/R4`
- `[NHS docs]` production: `https://api.service.nhs.uk/personal-demographics/FHIR/R4`

| Path | Method | Purpose |
|---|---|---|
| `/Patient/<nhs_number>` | GET | Retrieve a Patient resource by NHS number |
| `/Patient?<demographic params>` | GET | Search for patients by demographic parameters (returns Bundle) |
| `/metadata` | GET | FHIR CapabilityStatement |

`[sandbox]` The sandbox is a **single-fixture mock**: it only meaningfully
recognises NHS number `9000000009`. Other NHS numbers return a proper 404
OperationOutcome. The search endpoint returns a warning-shaped
OperationOutcome (see "Sandbox behavioural quirks" below) for any input.

### Auth model

`[sandbox]` The sandbox is **completely unauthenticated**: no OAuth2,
no API key, no Authorization header. The only mandatory authentication-
adjacent header is `X-Request-ID` (see below). This makes sandbox
development fast but means the sandbox cannot be used to validate the
production auth flow.

`[NHS docs]` Production and integration environments use
**application-restricted access mode**: OAuth2 with a signed JWT bearer
token. The JWT is signed with a private key whose public key is
registered with NHS Digital during onboarding. Tokens are obtained from
the OAuth endpoint and presented as `Authorization: Bearer <token>` on
each request. Token lifetime and refresh behaviour have not yet been
verified against the integration environment.

Implication for client design: the request *shape* is identical between
sandbox and production — only the auth wrapper differs. A PDS client
can be developed entirely against the sandbox and have OAuth bolted on
as a request-signing middleware when moving to integration.

### Mandatory headers

`[sandbox]` Every request must include:

| Header | Value | Purpose |
|---|---|---|
| `X-Request-ID` | A fresh UUID per request | Spine correlation ID. Spine rejects calls without it. |
| `Accept` | `application/fhir+json` | Negotiates FHIR JSON response |

A missing `X-Request-ID` returns:

- Status: `400 Bad Request`
- Body: OperationOutcome with `code: required`, Spine error code `MISSING_VALUE`, diagnostics `"Invalid request with error - X-Request-ID header must be supplied to access this resource"`

`[NHS docs]` Production additionally requires:

- `Authorization: Bearer <jwt>` (see Auth model)
- `X-Correlation-ID` may be present alongside `X-Request-ID`; semantics not yet investigated

### GET Patient by NHS number

`[sandbox]` Request:

```
GET /Patient/9000000009
X-Request-ID: <uuid>
Accept: application/fhir+json
```

Successful response:

- Status: `200 OK`
- Body: a FHIR `Patient` resource (see "Patient resource shape" below)

NHS-number-not-found response:

- Status: `404 Not Found`
- Body: an `OperationOutcome` (see "OperationOutcome shape" below) with:
  - `issue[].severity: "information"` (note: **not** `"error"`)
  - `issue[].code: "not-found"`
  - `details.coding[].code: "RESOURCE_NOT_FOUND"`

Malformed NHS number response (e.g. non-numeric):

- Status: `400 Bad Request`
- Body: OperationOutcome with:
  - `issue[].severity: "error"`
  - `issue[].code: "value"`
  - `details.coding[].code: "INVALID_RESOURCE_ID"`

### Search Patient by demographics

`[NHS docs]` Standard FHIR search semantics, with query parameters like
`family=`, `given=`, `birthdate=`, `gender=`, `address-postalcode=`,
`fuzzy-match=true`.

`[sandbox]` **Demographic search is effectively unusable in the
sandbox.** Regardless of inputs, the sandbox returns:

- Status: `200 OK` (note: **not** an error status)
- Body: OperationOutcome with:
  - `issue[].severity: "warning"`
  - `issue[].code: "not-supported"`
  - `issue[].diagnostics: "This mock endpoint has no example response for this combination of search parameters"`

This is a sandbox limitation, not a real PDS error condition. Production
PDS returns a real FHIR `Bundle` of matching `Patient` resources.

### Sandbox behavioural quirks (very important for client design)

`[sandbox]`

1. **HTTP 200 + warning body is a real combination.** The sandbox can
   return an `OperationOutcome` with `severity: "warning"` and HTTP 200.
   A client that branches on HTTP status alone will treat the response as
   a successful empty result. The client **must inspect the response body
   type** to differentiate a real `Patient`/`Bundle` from an
   `OperationOutcome`.

2. **The metadata endpoint returns an empty body with HTTP 200.** We
   cannot use it for capability discovery. Hand-code the operations the
   client uses.

3. **The sandbox is essentially a fixture lookup keyed by NHS number.**
   Only `9000000009` returns a populated Patient. Other valid-shaped NHS
   numbers return a proper 404. This is enough to develop the GET path
   but not enough to test demographic-search-and-disambiguate flows —
   those need the integration environment or hand-built fixtures.

4. **The sandbox fixture is deliberately pathological.** Patient
   `9000000009` carries multiple "do not deliver" signals simultaneously
   (see "Clinical safety: deliverability decision tree" below). This is
   intentional: the sandbox is designed to catch developers who skip
   safety validation. Treat the canonical fixture as a *negative* test
   case, not a happy-path example.

### Patient resource shape

`[sandbox]` The raw JSON for NHS number `9000000009` is stored as a test
fixture in the repo (`tests/fixtures/pds_patient_9000000009.json`, to be
captured during Phase 1b implementation). This section documents the
fields and FHIR paths we consume.

Key identifier systems (used as constants in the client):

| Concept | System URL |
|---|---|
| NHS number | `https://fhir.nhs.uk/Id/nhs-number` |
| ODS organization code | `https://fhir.nhs.uk/Id/ods-organization-code` |
| Spine error code | `https://fhir.nhs.uk/R4/CodeSystem/Spine-ErrorOrWarningCode` |
| Death notification status | `https://fhir.hl7.org.uk/CodeSystem/UKCore-DeathNotificationStatus` |
| Removal from registration | `https://fhir.nhs.uk/CodeSystem/PDS-RemovalReasonExitCode` |

Key fields we consume from a `Patient` resource:

| Field | FHIR path | What it means |
|---|---|---|
| Confidentiality flag | `meta.security[].code` | `"U"` = unrestricted (deliverable); `"R"` or `"V"` = restricted/very restricted (S-flag — do not deliver) |
| Death indicator | `deceasedDateTime` or `deceasedBoolean` | Presence indicates deceased patient |
| Formal death notification | `extension[url=...DeathNotificationStatus].extension[url=deathNotificationStatus].valueCodeableConcept.coding[].code` | Codes `1` (informal) or `2` (formal) indicate death notification received |
| Removal from registration | `extension[url=...RemovalFromRegistration]` | Presence with no `effectiveTime.end` (or end in future) indicates removed from English GP registration |
| Registered GP | `generalPractitioner[].identifier.value` | The ODS code of the registered GP practice |
| GP registration period | `generalPractitioner[].identifier.period.start` / `.period.end` | When this GP registration was/is active |
| Managing organisation | `managingOrganization.identifier.value` | Currently observed to match `generalPractitioner` in the sandbox |

`[sandbox]` **Critical structural pattern**: many fields are arrays of
period-bounded entries. `name`, `address`, `telecom`, and
`generalPractitioner` all follow this pattern. Each entry has
`period.start` and (optionally) `period.end`. **Never use array index
`[0]` to pick an entry**; always filter to the currently-active entry
(period.end absent or in the future, and period.start in the past or
absent).

The sandbox fixture deliberately includes historic entries with
`period.end` in the past, alongside no current entry, to catch
developers who skip this filter.

### Clinical safety: deliverability decision tree

`[sandbox]` The sandbox fixture for `9000000009` carries multiple
independent "do not deliver" signals:

- `meta.security.code: "U"` (unrestricted — OK on this dimension)
- `deceasedDateTime: "2010-10-22T00:00:00+00:00"` (deceased)
- `extension[DeathNotificationStatus].code: "2"` (formal death notice received)
- `extension[RemovalFromRegistration].code: "SCT"` (transferred to Scotland)
- `generalPractitioner[0].identifier.period.end: "2021-12-31"` (registration ended in the past — no current GP)

Yet `generalPractitioner` is still populated. **A naive extractor that
simply reads `Patient.generalPractitioner[0].identifier.value` will
happily try to deliver clinical documents to a GP practice that hasn't
been the patient's GP for years, concerning a patient who has been dead
since 2010.** This is the central clinical-safety hazard the sandbox is
designed to expose.

The deliverability check must run in this order, short-circuiting on
the first failure:

1. **Security flag**: `meta.security[].code` — if `"R"` or `"V"`,
   abort (S-flagged patient).
2. **Deceased flag**: `deceasedDateTime` or `deceasedBoolean` —
   if present, abort.
3. **Death notification extension**: if the
   `Extension-UKCore-DeathNotificationStatus` extension exists with a
   non-null status code, abort.
4. **Removal from registration**: if the
   `Extension-PDS-RemovalFromRegistration` extension exists with no
   `effectiveTime.end` or an end in the future, abort.
5. **Active GP**: scan `generalPractitioner[]` for an entry where
   `identifier.period.end` is absent or in the future, AND
   `identifier.period.start` is absent or in the past. If none found,
   abort (no currently-registered GP).
6. **Extract ODS code**: from the active GP entry,
   `identifier.value` is the ODS code to use as the MESH/GP Connect
   recipient.

Each abort condition should produce a distinct, named outcome
(`PATIENT_RESTRICTED`, `PATIENT_DECEASED`, `PATIENT_DECEASE_NOTIFIED`,
`PATIENT_DEREGISTERED`, `PATIENT_NO_ACTIVE_GP`) so the fallback layer
can log and the operator can understand why electronic delivery did not
proceed. This is a clinical-safety surface and the failure reasons are
clinically meaningful, not implementation-internal.

### OperationOutcome shape

`[sandbox]` All error and warning responses use the same OperationOutcome
structure:

```json
{
  "resourceType": "OperationOutcome",
  "issue": [
    {
      "severity": "error" | "warning" | "information",
      "code": "<fhir-issue-code>",
      "details": {
        "coding": [
          {
            "system": "https://fhir.nhs.uk/R4/CodeSystem/Spine-ErrorOrWarningCode",
            "version": "1",
            "code": "<spine-error-code>",
            "display": "<human readable>"
          }
        ]
      },
      "diagnostics": "<optional message>"
    }
  ],
  "timestamp": "<optional ISO-8601, present on warnings>"
}
```

Note that for 404 responses, `severity` is `"information"`, not
`"error"`. The HTTP status code and the FHIR severity do not always
align — another reason the client must inspect both.

### Spine error codes (observed)

`[sandbox]`

| HTTP | `severity` | `issue.code` | Spine `code` | Meaning | Retry? |
|---|---|---|---|---|---|
| 200 | `warning` | `not-supported` | (none) | Sandbox-only: mock has no example for this query | No (sandbox quirk) |
| 400 | `error` | `value` | `INVALID_RESOURCE_ID` | The path parameter (e.g. NHS number) is malformed | No (our bug; log critical) |
| 400 | `error` | `required` | `MISSING_VALUE` | A required header is missing | No (our bug; log critical) |
| 404 | `information` | `not-found` | `RESOURCE_NOT_FOUND` | NHS number is well-formed but no patient exists | No (terminal; trigger fallback) |

`[NHS docs]` Production will additionally surface (not yet observed):

- `INVALID_NHS_NUMBER` — checksum failure on the NHS number
- `INVALID_SEARCH_DATA` — malformed search parameters
- `ACCESS_DENIED` — auth scope insufficient for the requested operation
- `INTERNAL_SERVER_ERROR` (5xx)
- Rate limit responses (429 — exact format not yet investigated)

### Known sandbox limitations vs production

`[sandbox]`

- Sandbox is a single-fixture mock; only `9000000009` returns real data.
- No authentication, so the OAuth2/JWT flow cannot be tested.
- Demographic search is not implemented; the search endpoint returns a not-supported warning regardless of input.
- The metadata endpoint returns empty.
- Rate limits and 5xx behaviour cannot be exercised.
- No support for `If-Match` / optimistic-concurrency headers (we don't use these as a read-only client, but worth noting).

### Useful undocumented observations

`[sandbox]`

- `meta.versionId` is present on the Patient resource (`"2"` for the canonical fixture). Used for optimistic concurrency on updates; not relevant to our read-only use case.
- The `multipleBirthInteger` field is `1` in the fixture, which is a slightly odd value (1 implies "first of multiple", but multiple-birth context is otherwise absent). Treat this field as informational only.
- The `birthDate` and `deceasedDateTime` in the canonical fixture are set to the same date (`2010-10-22`), suggesting a stillbirth or neonatal death scenario. This is intentional sandbox seeding.
- Address entries include `Extension-UKCore-AddressKey` extensions carrying PAF (Postcode Address File) and UPRN (Unique Property Reference Number) identifiers. We do not consume these.

### Still open (to be investigated against PTL/integration)

The sandbox cannot answer these. They will be settled during integration-
environment onboarding.

- OAuth2 token endpoint URL, JWT signing requirements, token lifetime, refresh model.
- Rate limit headers and 429 response format.
- 5xx behaviour and recommended retry/backoff strategy.
- Demographic search Bundle response shape (the FHIR spec defines it; PDS may add extensions).
- Whether the production response includes any fields the sandbox does not (e.g. additional extensions for nominated pharmacy, language preferences in different shapes).
- The catalogue of test patients available in the integration environment and which clinical-safety branch each one exercises.

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
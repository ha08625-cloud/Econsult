# MESH Integration Plan

## Document Status

This document supersedes a previous version that included a PDS lookup phase. PDS lookup has been removed from the plan entirely; the prior version is retrievable from git history if needed. The receiving GP practice is determined by deployment configuration (the practice owns the deployment that serves the form), not by patient-side lookup. The NHS number, when supplied by the patient, is treated as opaque data attached to the PDF for the GP's reference. It is not validated against PDS.

**Revision (June 2026):** workflow ID research (see `docs/nhs_integration_reference.md`, "Workflow IDs") established that there is no registered, non-deprecated MESH workflow ID for raw PDF delivery to a GP practice's clinical system; the two active consultation-report workflow IDs both belong to GP Connect Send Document and require an ITK3/FHIR payload. The raw-PDF payload built by this plan is therefore **provisional**, contingent on a locally agreed workflow arrangement with the first practice. The dispatcher is insulated from this question via the `MeshPayloadBuilder` seam (Phase 3). Two parallel tickets hedge the alternative outcomes: a dormant PDS client library and a GP Connect Send Document spike + payload builder (see "Out of Scope" below). Production enablement is gated on the practice/NHS Digital answer — see "Production enablement gates" under Phase Sequencing.

## Sandbox

A local MESH sandbox is installed in `sandbox/` (NHSDigital/mesh-sandbox v1.0.54, run via `make sandbox-up`). It can be used to clarify protocol-level questions as the plan is refined further. See `sandbox/README.md` for usage.

The sandbox investigation in the prior planning round confirmed:

- The MESH API uses a tracking-by-messageID model, not a receipt model. The original "inbox poller + receipt parser" design was replaced with a "tracking poller" (Phase 4 below).
- Successful sends return HTTP 202 Accepted with body `{"messageID": "<32-char-hex>"}`.
- `Mex-LocalID` round-trips through the tracking endpoint, but there is no way to enumerate sent messages by it — limiting its usefulness for automatic crash recovery (see "Accepted Limitations").
- Auth headers must be regenerated per request (timestamp granularity is one minute).
- Recipient acknowledgement is the authoritative delivery signal. `downloadTimestamp` populated alone is not sufficient.

PDS sandbox investigation (since the prior round) confirmed that PDS lookup adds no useful capability to this system. That is why this revision drops PDS entirely.

---

## Governing Decisions

- MESH delivery is controlled by a single process-level env var `MESH_DELIVERY` (`0` or `1`). Single-practice, single-tenancy deployment for the foreseeable future. The `MESH_DELIVERY=0` path is the email path and is unchanged from current production behaviour; the `MESH_DELIVERY=1` path is what this plan builds.
- `MESH_DELIVERY` is read once at process startup. It is never re-read inside hot loops. A misconfigured deployment must fail at startup, not silently degrade. This requirement is already enforced in Phase 1a (shipped).
- **The receiving practice is determined by deployment configuration**, not by patient-side lookup. Each deployment serves exactly one practice. The destination MESH mailbox ID is therefore a deployment-controlled env var (`MESH_RECIPIENT_MAILBOX_ID`), read once at the PDF worker's startup and applied to every submission this process handles. It is deliberately **not** stored in `practices` or surfaced in the admin UI: a wrong recipient does not bounce like a mistyped email, it silently misroutes a clinical referral to the wrong NHS mailbox (or is rejected as an unregistered recipient). A write-once, clinically-sensitive routing value behind a self-service UI with shape-only validation is exactly the silent-misroute failure the Fail-Fast Configuration invariant exists to prevent, so it stays in the deployment-controlled, `_require_env`-guarded path. The value is copied onto each `mesh_jobs` row at enqueue time so a config change between enqueue and dispatch cannot misroute an already-queued referral.
- **Delivery channel hierarchy:**
  1. **MESH** — primary delivery path when `MESH_DELIVERY=1`.
  2. **Mailgun HTTPS API** — secondary path. Used as fallback on terminal MESH failure.
  3. **SMTP** — break-glass legacy path only. Activated manually when both MESH and Mailgun are unavailable. Submissions delivered via SMTP are retained, not deleted, so operators can audit them once primary paths recover.
- The existing `pdf_worker.py` is unchanged in its core logic from Phase 1a. The polymorphic seam (`DownstreamEnqueuer`) gains a second implementation: `MeshEnqueuer`, which writes to `mesh_jobs` rather than `delivery_jobs`. The PDF worker itself remains downstream-agnostic.
- Sequential pipeline: Router → PDF → MESH (with Mailgun fallback on terminal MESH failure). No PDS hop. No FHIR build hop in the default plan (see "Payload status: provisional" below).
- **Payload construction is behind a seam.** The dispatcher builds its payload via the `MeshPayloadBuilder` interface (Phase 3). `RawPdfPayloadBuilder` is the only implementation this plan ships; `GpConnectSendDocumentPayloadBuilder` is a separate ticket. The dispatcher itself is payload-agnostic: queue handling, retry, fallback, and tracking are unchanged whichever builder is wired.
- **Mailgun fallback emails are identical to email-path emails** (same subject, same body, same attachment). `is_fallback` is operational metadata only; no code in `delivery_worker.py` or `delivery_service.py` reads it. (Resolves former Open Item 4.)
- All workers are separate processes for clarity and clean log separation.
- **Delivery confirmation requires recipient acknowledgement.** The tracking poller transitions `mesh_jobs.status` to `delivered` only when the tracking record shows `status == "Acknowledged" AND statusSuccess == "SUCCESS"`. Clinical referrals are not deleted until we have positive proof of recipient processing.

## Accepted Limitations

- **Duplicate-send on dispatcher crash.** If the dispatcher POSTs to Spine, Spine accepts (202), but the dispatcher crashes before committing the returned `message_id` to `mesh_jobs`, the next dispatcher run will resend the same submission. The GP practice receives two copies. This is documented and accepted. `Mex-LocalID` is still set per POST so an operator can manually correlate duplicates via the tracking endpoint when investigating.
- **Transport acknowledgement is not clinical-layer proof.** A MESH tracking status of `Acknowledged` means the recipient's MESH client acknowledged receipt at the transport layer. It does not prove the document was processed by, or is visible in, the practice's clinical system (NHS developer forums document raw PDFs arriving in mailboxes without surfacing to the GP — see `docs/nhs_integration_reference.md`). Mitigation is procedural, not technical: the workflow arrangement is agreed in writing with the practice, and the verified-first-send gate (see Production enablement gates) requires a named human at the practice to confirm visibility before real patient traffic.
- **Stuck-in-provider_accepted submissions.** If a GP practice's MESH client downloads but never acknowledges, the submission remains in `provider_accepted` indefinitely from our point of view. Detection is by elapsed-time alerting (24h warning, 72h error). Resolution is operator-driven: confirm out-of-band, then transition the row manually using the SQL script in Phase 5.

## Out of Scope (Explicitly Deferred)

These are intentionally not part of any phase in this document. Each is genuinely useful but separable, and deferring keeps the plan focused.

- **NHS Login.** Patient-side identity verification. If adopted later, an `assurance_level` column on `submission_records` may be needed to record verification confidence. That decision is deferred. The current schema is forward-compatible with adding such a column non-destructively.
- **GP Connect Send Document.** Now tracked as a separate ticket (`ticket_gpconnect_payload_builder.md`): a spike to resolve applicability and version, then a `GpConnectSendDocumentPayloadBuilder` behind the Phase 3 seam. ITK3 acknowledgement handling remains deferred beyond that ticket. See "Payload status: provisional" below.
- **PDS lookup (dormant client library).** Removed from this pipeline for the reasons stated in the document status note. Now additionally tracked as a separate ticket (`ticket_pds_client_library.md`) building an unwired client library only — a hedge against GP Connect's patient-based addressing requirement. The fuzzy-match resolution policy (the clinically hard part) is explicitly out of that ticket's scope.
- **NHS number client-side validation (Mod-11).** Worthwhile as a frontend UX improvement; tracked as a separate frontend ticket. Not part of this delivery plan.

### Payload status: provisional

(Supersedes the former "Deferred: FHIR/ITK3 envelope" section. The framing has inverted since the June 2026 workflow ID research — see `docs/nhs_integration_reference.md`, "Workflow IDs".)

- Raw MESH transport does not require a FHIR envelope at the transport level. However, there is no registered, non-deprecated workflow ID for raw PDF delivery to a GP practice; the deprecated Kettering XML route (`DISCH_KET`) must not be used. Raw PDF is therefore viable in production **only** under a locally agreed workflow ID arrangement with the receiving practice, with practice-side handling confirmed.
- The likely production endgame is GP Connect Send Document (or a successor standard — see the scope caveat below). Adopting it drags in three things beyond a payload builder: (1) the ITK3 acknowledgement model — infrastructure and business acks arrive as MESH messages under the `_ACK` responder workflow IDs, which reintroduces inbox handling and changes the Phase 4 tracking design; (2) sender accreditation/assurance; (3) patient-based addressing (`GPPROVIDER_<NhsNo>_<DOB>_<Surname>`), which requires the patient's NHS number, DOB, and surname at send time — implying either mandatory NHS number entry (poor UX, reopens a governing decision) or a server-side PDS trace (see `ticket_pds_client_library.md`; note PDS fuzzy-match brittleness is a known operational reality in practice).
- **Scope caveat:** GP Connect Send Document v1's stated scope is consultations that took place *outside* the patient's regular practice (federated/hub working). Our use case — a patient submitting to their own practice — does not match that scope; v2 broadens to any document type but is in public beta. Whether GP Connect Send Document, a locally agreed raw-document arrangement, or a different standard altogether is the correct route for practice-own online consultation intake is a question for NHS Digital and the first practice, and cannot be resolved by further desk research.
- Phase 3 therefore ships the `MeshPayloadBuilder` seam as concrete code with `RawPdfPayloadBuilder` as the provisional implementation. The out-of-band questions (practice IT, NHS Digital / system supplier) start immediately and in parallel with Phase 3 coding; their answers are required before Phase 4 planning (acknowledgement model) and before production enablement (workflow arrangement).

---

## Phase Sequencing

```
Phase 1a (adapter refactor)              [SHIPPED]
    -> Phase 1b (local mTLS PKI + sandbox proxy)  [SHIPPED]
        -> Phase 2a (MESH client library)
            -> Phase 2b (schema + MeshEnqueuer + wiring)
                -> Phase 3 (MESH dispatcher + Mailgun fallback)
                    -> Phase 4 (tracking poller + deletion job rewrite)
                        -> Phase 5 (observability + operator tooling)
```

- Phase 1a is already done. It is the polymorphic seam (`DownstreamEnqueuer`) in the PDF worker, plus the strict `MESH_DELIVERY` env validation. `MESH_DELIVERY=1` currently refuses to start because no implementation exists yet.
- Phase 1b is also done. It establishes the local-dev mTLS parity: a dev PKI, an nginx mTLS-terminating proxy in front of the sandbox container, and the documentation/env-var canonicalisation that downstream phases rely on. No application code.
- Phase 2a is a pure code library — no DB schema, no worker, no wiring. It exercises the MESH protocol against the sandbox in tests and can ship on its own.
- Phase 2b adds migration 0005 (the `mesh_jobs` table and `delivery_jobs.is_fallback` column), the `MeshEnqueuer` adapter, and the wiring in `pdf_worker_main.py` so `MESH_DELIVERY=1` no longer aborts startup (with `MESH_RECIPIENT_MAILBOX_ID` as a required fail-fast env var). After Phase 2b, the PDF worker can enqueue `mesh_jobs` rows but nothing consumes them yet.
- Phase 3 adds the dispatcher worker that consumes `mesh_jobs` and POSTs to MESH, including the `MeshPayloadBuilder` seam, the Mailgun fallback when MESH terminally fails, and the orphaned-fallback recovery sweep.
- Phase 4 adds the tracking poller (delivery confirmation) and rewrites `deletion_job.py` to be MESH-status-aware.
- Phase 5 covers Sentry alerts, operator SQL, and the deployment checklist.

Each phase is independently mergeable and reversible if needed.

### Production enablement gates

Mergeable is not the same as enableable. `MESH_DELIVERY=1` must NOT be set in production until ALL of the following hold:

1. **Phase 4 is deployed.** With Phase 3 alone, MESH-path submissions are never confirmed (rows sit at `sent` forever) and never become deletion-eligible (`deletion_job.py` joins on `delivery_jobs` only), giving unbounded retention of clinical photos and PDFs.
2. **The workflow arrangement is confirmed in writing** with the first practice: which workflow ID their mailbox is configured for, and what their MESH client / clinical system does with the payload format we send.
3. **The endpoint lookup check passes** (`/endpointlookup/<ODS>/<workflow_id>` returns the practice's mailbox for the agreed workflow ID).
4. **A verified first send has completed:** one test referral sent end-to-end, with a named human at the practice confirming the document is visible in their working clinical workflow — not merely that MESH tracking shows `Acknowledged`. This step is permanent deployment-checklist content for every new practice, not a one-off.

Phase 5 should also document a drain procedure: flipping `MESH_DELIVERY` from 1 back to 0 strands any pending `mesh_jobs` rows with no consumer. The email delivery worker must remain deployed while `MESH_DELIVERY=1` — it is the fallback consumer.

---

## Phase 1a — PDF Worker Adapter Refactor (SHIPPED)

Documented for completeness. See git history for details. Summary of what landed:

- New file `app/services/delivery/downstream_enqueuer.py` defining the `DownstreamEnqueuer` Protocol and the `DeliveryEnqueuer` (email path) implementation.
- New method `PDFRepository.get_delivery_email(submission_id)`.
- `pdf_worker.py` step 2 changed from `delivery_repo.create_job(...)` to `downstream.enqueue(submission_id=...)`.
- `pdf_worker_main.py` wires `DeliveryEnqueuer` unconditionally when `MESH_DELIVERY=0`. It refuses to start when `MESH_DELIVERY=1` with the message "MESH_DELIVERY=1 is not yet supported. Phase 1a only implements the email path."
- `main.py._validate_startup` enforces `MESH_DELIVERY` presence and `{"0", "1"}`-only values.
- Sentry tag `downstream_mode=email` is set at worker startup.

No schema changes, no runtime behaviour change.

---

## Phase 1b — Local mTLS PKI and Sandbox Proxy (SHIPPED)

A pure infrastructure phase: no application code, no DB schema. Establishes the local-dev mTLS parity needed before any `MeshClient` work.

### 1b.1 Strategic decision

MESH production requires mutual TLS. The NHSDigital `mesh-sandbox` Docker image does not enforce mTLS natively — its uvicorn process is launched with server-cert flags only (see `docs/nhs_integration_reference.md`). To exercise the production mTLS code path on every local request, the sandbox runs behind an nginx mTLS-terminating proxy.

The `MeshClient` (Phase 2a) therefore unconditionally presents a client certificate and unconditionally verifies the server. There is no special-case skip for sandbox. Three strict string paths — `ca_cert_path`, `client_cert_path`, `client_key_path` — are mandatory constructor inputs to the client. No `None`, no boolean toggle, no environment-name-driven bypass.

### 1b.2 Files

New:
- `sandbox/certs/generate.sh` — idempotent OpenSSL script generating the dev PKI.
- `sandbox/certs/sandbox_ca.{pem,key}`, `sandbox_server.{pem,key}`, `sandbox_client.{pem,key}` — committed dev PKI. See `sandbox/certs/README.md` for the rationale.
- `sandbox/certs/README.md`
- `sandbox/nginx/nginx.conf` — TLS termination + client-cert validation + reverse proxy.

Modified:
- `sandbox/docker-compose.yml` — adds the nginx service, removes the host port from `mesh_sandbox`, creates an internal `mesh_net` bridge network, depends_on `service_healthy`.
- `sandbox/README.md` — rewritten for the mTLS topology. Stale references removed: `mesh_inbox_worker.py`, `MESH_ENV`, `MESH_URL`, `SENDER_ODS_CODE`, `TARGET_ODS_CODE`, the `X26`-in-production `main.py` guard.
- `Makefile` — `sandbox-check` target passes the dev CA, cert, and key to curl.
- `docs/arch_security.md` — new Section 8 "MESH Outbound TLS" describing strategy, strict-path inputs, fail-fast invariant, and parity limits.
- `docs/nhs_integration_reference.md` — expanded sandbox-limitations TLS bullet capturing the uvicorn-command-line evidence that the sandbox cannot enforce mTLS.

### 1b.3 Canonical env var names

These names are used from Phase 2a onwards. Earlier drafts of this plan referenced `MESH_ENV`, `MESH_URL`, `MESH_CERT_PATH`, `MESH_KEY_PATH`, `SENDER_ODS_CODE`, `TARGET_ODS_CODE` — all are superseded.

| Variable | Purpose |
|---|---|
| `MESH_DELIVERY` | `0` or `1`. Shipped in Phase 1a. |
| `MESH_BASE_URL` | e.g. `https://localhost:8700` (sandbox) or the production base URL. |
| `MESH_MAILBOX_ID` | Sender mailbox ID. |
| `MESH_RECIPIENT_MAILBOX_ID` | Destination practice mailbox ID. Required when `MESH_DELIVERY=1`; read by the PDF worker and copied onto each `mesh_jobs` row at enqueue time. Deployment-controlled (never set via the admin UI) — see Governing Decisions. |
| `MESH_MAILBOX_PASSWORD` | Input to the HMAC over the auth canonical string. |
| `MESH_SHARED_KEY` | HMAC secret. |
| `MESH_CA_CERT_PATH` | Path to CA bundle for verifying the server certificate. |
| `MESH_CLIENT_CERT_PATH` | Path to our client certificate. |
| `MESH_CLIENT_KEY_PATH` | Path to our client private key. |
| `MESH_WORKFLOW_ID` | Workflow ID for outgoing messages (introduced in Phase 3). |

### 1b.4 Parity limits

The nginx sidecar catches the most common mTLS mistakes: failing to present a cert, presenting one signed by the wrong CA, failing to verify the server cert against the expected CA. It does not catch Spine-specific quirks such as cipher-suite restrictions, peer-cert subject-DN validation, or revocation checks. First contact with NHS PTL may surface issues invisible to the local sandbox; this is an accepted limitation of any local mTLS emulation.

---

## Phase 2a — MESH Client Library (SHIPPED)

A pure client library: no DB schema, no worker process, no wiring.
`MESH_DELIVERY=1` still aborts at startup (unchanged from Phase 1a). What
landed:

- New package `app/services/delivery/mesh/`:
  - `client.py` — the `MeshClient` class.
  - `errors.py` — `MeshError` and its subclasses `MeshTransientError` and
    `MeshTerminalError`.
  - `__init__.py` — re-exports all four names.
- `tests/test_mesh_client.py` — unit tests (no marker; runs in CI).
- `tests/test_mesh_client_integration.py` — DB-free sandbox integration tests.

Protocol facts (auth-header layout, endpoint paths, the query-string tracking
form, response and error shapes) live in `docs/nhs_integration_reference.md`,
which is authoritative. The client follows it; this plan does not restate it.

### Public API (consumed by Phases 3 and 4)

`MeshClient` is constructed with keyword-only arguments: `base_url`,
`mailbox_id`, `mailbox_password`, `shared_key`, the three mTLS paths
(`ca_cert_path`, `client_cert_path`, `client_key_path`), and an optional
`timeout` (default 30s). It reads **no** environment variables — the Phase 3
worker entry point reads the env and passes explicit values. The constructor
builds one `requests.Session` (with `cert` and `verify` set) and does **not**
touch the filesystem; validating that the three cert files exist on disk is the
Phase 3 `mesh_worker_main.py` fail-fast (`docs/arch_security.md` section 8).

Methods:

- `handshake() -> None` — POSTs the startup handshake; raises on failure.
  Phase 3 calls it once at process startup, before the loop.
- `send_message(*, recipient_mailbox_id, payload_bytes, workflow_id, mex_localid, content_type) -> str`
  — returns the MESH `messageID`. **Store it verbatim as `TEXT`.** It is a
  32-character uppercase hex string and must not be normalised; parsing it as a
  UUID lowercases and hyphenates it, which would no longer match the value the
  tracking endpoint echoes back.
- `get_message_status(*, message_id) -> dict` — returns the parsed tracking
  JSON. Phase 4 reads `status`, `statusSuccess`, and `downloadTimestamp` from
  it.

### Error contract (what the Phase 3 dispatcher branches on)

- `MeshTransientError` — retryable. Transport/network failures, 5xx, and a 403
  with an empty `errorCode` (auth/clock). Phase 3 retries with backoff, then
  falls back to email after `MAX_MESH_ATTEMPTS`.
- `MeshTerminalError` — not retryable. A 403 with a populated `errorCode`, any
  other 4xx (including 417 "unregistered recipient"), and malformed or
  unparseable success bodies. Phase 3 falls back to email immediately.

The exception classes are attribute-free; their message string carries the HTTP
status and any MESH `errorCode`. If Phase 3 or 5 wants the error code as a
structured field (to populate `mesh_jobs.last_error_code` without parsing the
message), add it then — a small additive change to the exceptions and the
classification helper.

### Sandbox integration-test convention (Phases 3 and 4 follow this)

`tests/test_mesh_client_integration.py` is a **DB-free** integration test. It
carries `pytestmark = pytest.mark.integration` (so it stays out of `make test`
and self-skips in CI) but deliberately **omits the `TEST_DATABASE_URL`
guardrail**, because it talks to the MESH sandbox over HTTP, not Postgres. It is
guarded solely on `MESH_BASE_URL` (module-level skip if unset); the remaining
MESH env vars are read with a direct `os.environ[...]` subscript so a
half-configured `.env.sandbox` fails loudly. The Phase 3 and Phase 4 sandbox
integration tests follow the same pattern. This is the one documented exception
to the "every integration module carries the `TEST_DATABASE_URL` guardrail"
rule in `docs/arch_testing.md`.

---

## Phase 2b — Schema, MeshEnqueuer, and Wiring

This phase makes `MESH_DELIVERY=1` a startable configuration. The PDF worker writes to `mesh_jobs` instead of `delivery_jobs`. Nothing consumes `mesh_jobs` yet; that is Phase 3.

### 2b.1 Migration `0005_mesh_schema.py`

(Renamed from `0005_mesh_fhir_schema` since the FHIR builder is no longer in scope.)

Creates the `mesh_jobs` table and adds `is_fallback` to `delivery_jobs`. Single migration, single transaction — there is no separate practice-mailbox migration (the recipient is an env var, not a `practices` column; see Governing Decisions).

#### `mesh_jobs`

One row per MESH-enabled submission. Created by the PDF worker (via `MeshEnqueuer`). Consumed by the MESH dispatcher (Phase 3).

| Column | Type | Constraints |
|---|---|---|
| id | UUID | PRIMARY KEY DEFAULT gen_random_uuid() |
| submission_id | TEXT | NOT NULL UNIQUE REFERENCES submission_records(submission_id) |
| status | TEXT | NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'sent', 'provider_accepted', 'delivered', 'failed', 'fallback_triggered')) |
| message_id | TEXT | UNIQUE — set by dispatcher when MESH returns 202 |
| mex_localid | UUID | NOT NULL DEFAULT gen_random_uuid() — set on row creation for crash-trail correlation |
| recipient_mailbox_id | TEXT | NOT NULL — copied from the `MESH_RECIPIENT_MAILBOX_ID` env value at enqueue time |
| attempt_count | INTEGER | NOT NULL DEFAULT 0 |
| last_error | TEXT | |
| last_error_code | TEXT | MESH error code from response body, if any |
| created_at | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |
| updated_at | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |
| next_retry_after | TIMESTAMPTZ | |
| sent_at | TIMESTAMPTZ | |
| provider_accepted_at | TIMESTAMPTZ | |
| delivered_at | TIMESTAMPTZ | |

Index on `(status, next_retry_after)` for dispatcher claim queries.

Note: `recipient_mailbox_id` is copied onto the row rather than re-read from the env value at dispatch time. This protects against the `MESH_RECIPIENT_MAILBOX_ID` configuration changing (via redeploy) between enqueue and dispatch (rare, but cheap to defend against).

#### `delivery_jobs.is_fallback`

```sql
ALTER TABLE delivery_jobs ADD COLUMN is_fallback BOOLEAN NOT NULL DEFAULT FALSE;
```

Set only by the MESH dispatcher when it gives up and falls through to Mailgun. The PDF worker never sets it. The PDF worker on the email path (`MESH_DELIVERY=0`) creates `delivery_jobs` rows with `is_fallback=FALSE` by default.

### 2b.2 New File: `app/repositories/mesh_repository.py`

Methods:
- `create_job(*, submission_id, recipient_mailbox_id) -> str` — INSERT with `ON CONFLICT (submission_id) DO NOTHING` to keep the call idempotent. Returns the row's `id` as a string, or the existing row's `id` on conflict.
- `claim_next_pending() -> dict | None` — `SELECT ... FOR UPDATE SKIP LOCKED` claim of the next dispatchable row, used by Phase 3.
- `mark_sent(*, mesh_job_id, message_id)` — transitions to `sent`, records `message_id` and `sent_at`.
- `mark_provider_accepted(*, mesh_job_id)`, `mark_delivered(*, mesh_job_id)` — used by Phase 4 tracking poller.
- `mark_failed(*, mesh_job_id, error, error_code, next_retry_after) -> int` — increments `attempt_count`, records the error fields and backoff, and **leaves status as `pending`** (a transient failure is reclaimed when the backoff expires, not moved to a terminal state). Returns the new `attempt_count` so the Phase 3 dispatcher can compare against `MAX_MESH_ATTEMPTS` and decide whether to retry or fall back — the repository does not own that threshold.
- `mark_fallback_triggered(*, mesh_job_id)` — transitions to `fallback_triggered` when the dispatcher falls through to Mailgun.
- `get(mesh_job_id) -> dict` — returns the full row; raises `MeshJobNotFound` if absent. The mutating `mark_*` methods also raise `MeshJobNotFound` when the id does not exist.

Note: the `failed` status is reserved for the Phase 4 tracking-time terminal signal (Error / `statusSuccess=FAILED`); the method that sets it is added in Phase 4. In Phase 2b only `create_job` is wired (by `MeshEnqueuer`); the claim and `mark_*` methods are built and integration-tested here but not yet called by any worker.

### 2b.3 New File: `app/services/delivery/mesh_enqueuer.py`

Class `MeshEnqueuer` implementing the `DownstreamEnqueuer` Protocol from Phase 1a.

Constructor takes `mesh_repo: MeshRepository` and `recipient_mailbox_id: str`. The mailbox ID is resolved once at the PDF worker's startup from `MESH_RECIPIENT_MAILBOX_ID` (see 2b.4) and passed in here.

`enqueue(submission_id)` calls `mesh_repo.create_job(submission_id=..., recipient_mailbox_id=self._recipient_mailbox_id)`. Returns `None`.

Note: `MeshEnqueuer` is a thinner adapter than `DeliveryEnqueuer` because the MESH path needs less information at this stage. No re-reads of `pdf_jobs` or `submission_records` — those happen in the dispatcher when it builds the MESH message.

### 2b.4 `pdf_worker_main.py` Wiring

Two distinct edits (not a one-for-one swap — the abort and the wiring live in different places):

**Edit A — relax the abort.** The `MESH_DELIVERY=1` abort lives in `_validate_mesh_delivery()`, which runs before any app modules are imported. Remove the abort so `"1"` is accepted; keep the presence and `{"0","1"}` checks. The MESH path's own required config is validated at the point of use in `main()` (Edit B).

**Edit B — wire the downstream in `main()`**, after the repositories are instantiated. The recipient is read from the env (fail-fast) on the MESH branch only; there is no practice lookup and no `app.state` (the worker is a standalone process whose practice context is the optional, cosmetic `PRACTICE_ID` used for PDF headers):
```python
# imports added to the deferred-import block alongside DeliveryEnqueuer:
#   from app.repositories.mesh_repository import MeshRepository
#   from app.services.delivery.mesh_enqueuer import MeshEnqueuer

if mesh_delivery == "1":
    recipient_mailbox_id = _require_env("MESH_RECIPIENT_MAILBOX_ID")
    mesh_repo = MeshRepository(database_url)
    downstream = MeshEnqueuer(
        mesh_repo=mesh_repo,
        recipient_mailbox_id=recipient_mailbox_id,
    )
    downstream_mode = "mesh"
else:
    downstream = DeliveryEnqueuer(
        pdf_repo=pdf_repo,
        submission_repo=submission_repo,
        delivery_repo=delivery_repo,
    )
    downstream_mode = "email"

sentry_sdk.set_tag("downstream_mode", downstream_mode)
```
The startup log line that previously hard-coded `downstream_mode=email` becomes path-dependent.

`main.py` change is limited to removing the `MESH_DELIVERY=1` abort in its `_validate_mesh_delivery()` — no mailbox check there. The recipient is consumed only by the PDF worker (at enqueue time, via `MeshEnqueuer`), not by the web service, so the web tier validates only `MESH_DELIVERY` presence and `{"0","1"}`, consistent with how it already leaves the rest of the MESH transport set to the worker mains.

### 2b.5 Recipient mailbox configuration

There is no practice-table column, repository method, or admin UI field for the recipient mailbox. The destination is the deployment-controlled env var `MESH_RECIPIENT_MAILBOX_ID` (see Governing Decisions for the clinical-safety rationale). It is required at PDF worker startup when `MESH_DELIVERY=1` (`_require_env`) and copied onto each `mesh_jobs` row at enqueue time. Changing it requires a redeploy, not a UI action — acceptable because a practice's MESH mailbox is allocated once and essentially never changes.

### 2b.6 Tests

- `tests/test_mesh_enqueuer.py` (new, unit tests, no DB). Same shape as `test_downstream_enqueuer.py`: mock the repo, assert forwarding of `submission_id` and the constructor's `recipient_mailbox_id`.
- `tests/integration/test_mesh_repository.py` (new, integration tests; placed with the other DB integration tests, carries the `integration` marker and the `TEST_DATABASE_URL` guardrail). Each method tested against a real DB.
- `tests/integration/test_pdf_worker_mesh_path.py` (new, integration test): exercises the full PDF-worker-through-`MeshEnqueuer` flow with a real DB and no dispatcher — asserts a `mesh_jobs` row is written (not a `delivery_jobs` row), the recipient is stamped, the ordering invariant holds, and re-processing is idempotent.

---

## Phase 3 — MESH Dispatcher + Mailgun Fallback

Adds the dispatcher worker that consumes `mesh_jobs` and POSTs to MESH via the `MeshPayloadBuilder` seam, with Mailgun fallback on terminal MESH failure and an orphaned-fallback recovery sweep.

### 3.1 New File: `app/services/delivery/mesh_payload.py`

Defines the payload seam:

- `MeshPayload` — a small frozen dataclass: `payload_bytes: bytes`, `content_type: str`.
- `MeshPayloadBuilder` — a Protocol with one method: `build(*, pdf_bytes: bytes) -> MeshPayload`.
- `RawPdfPayloadBuilder` — the provisional implementation: returns the PDF bytes unchanged with content type `application/pdf`.

The workflow ID stays env-driven (`MESH_WORKFLOW_ID`, read by the entry point), not a builder concern in this phase. Note for the GP Connect ticket: workflow ID and payload format are coupled in the GP Connect specs, so when a second builder is added, the builder/workflow-ID pairing should be validated at startup rather than left as two independently settable values.

### 3.2 New File: `app/services/delivery/mesh_worker.py`

Background worker loop. Each iteration: run the orphaned-fallback sweep, then claim and process one `mesh_jobs` row.

Per-claim sequence:
1. Read the attachment from `submission_attachments` (guaranteed present by the Phase 2b ordering invariant).
2. `payload = payload_builder.build(pdf_bytes=...)`.
3. `mesh_client.send_message(...)` with `recipient_mailbox_id` from the claimed row, `workflow_id` from config, `mex_localid = str(mesh_job.mex_localid)` (the column is a Postgres UUID; the client takes a string), and the payload's bytes and content type.
4. On 202: `mesh_repo.mark_sent(mesh_job_id, message_id)`. Loop continues.
5. On `MeshTransientError`: `mesh_repo.mark_failed(...)` with `next_retry_after = now + backoff` per `mesh_constants.py`. If the returned `attempt_count >= MAX_MESH_ATTEMPTS`, treat as exhausted and fall through to step 6; otherwise the row is reclaimed when backoff expires.
6. On `MeshTerminalError`, or on transient exhaustion: `mesh_repo.mark_fallback_triggered(...)`, then read `to_email` via `PDFRepository.get_delivery_email(submission_id)` and `condition_label`/`submitted_at` via a new narrow `SubmissionRepository` method (see below), then `delivery_repo.create_job(..., is_fallback=True)`. The existing delivery worker sends via Mailgun with an email identical to the email path (Governing Decisions). Sentry alert routing is Phase 5.

**Ordering invariant:** `mark_fallback_triggered` → `delivery_repo.create_job(is_fallback=True)`, in that order. Failing safe means a crash between the two leaves an undelivered-but-detectable state, never a double-channel send.

**Orphaned-fallback recovery sweep (ships in this phase, not Phase 5):** at the top of each loop iteration, find `fallback_triggered` rows with no matching `delivery_jobs` row and call `delivery_repo.create_job(..., is_fallback=True)` for each — the call is idempotent on `submission_id` (UNIQUE + ON CONFLICT DO NOTHING), so recovery is automatic and safe under races. Log at ERROR when the sweep recovers a row; the Sentry event for it is added in Phase 5. Without this sweep in Phase 3, a dispatcher crash in the invariant window would leave a referral silently undelivered until Phase 5 ships.

**Metadata access:** the dispatcher does not call `SubmissionRepository.get_submission` (which returns the full row including clinical JSON). A new narrow method `SubmissionRepository.get_delivery_metadata(submission_id) -> dict` returns only `condition_label` and `submitted_at`. This is a deliberate, documented deviation from the delivery worker's stricter "never read submission_records" rule: the email path denormalises at enqueue time, the MESH fallback path reads narrowly at fallback time. Record the deviation in `arch_submission.md`.

### 3.3 New File: `mesh_constants.py`

Mirrors `delivery_constants.py`:

- `MESH_RETRY_BACKOFF_MINUTES: list[int] = [1, 5, 15]`
- `MAX_MESH_ATTEMPTS: int = len(MESH_RETRY_BACKOFF_MINUTES) + 1  # 4`
- `HANDSHAKE_RETRY_DELAYS_SECONDS: list[int] = [10, 30, 60, 120, 300]`

The MESH retry window (~21 minutes) is deliberately shorter than the email path's (~71 minutes): a working fallback exists, so prolonged MESH retries only delay the practice receiving the form.

### 3.4 New File: `mesh_worker_main.py`

Entry point. Validates env vars: `MESH_BASE_URL`, `MESH_MAILBOX_ID`, `MESH_MAILBOX_PASSWORD`, `MESH_SHARED_KEY`, `MESH_CA_CERT_PATH`, `MESH_CLIENT_CERT_PATH`, `MESH_CLIENT_KEY_PATH`, `MESH_WORKFLOW_ID`. For each of the three cert paths, validates the file exists on disk before instantiating `MeshClient` (fail-fast per `docs/arch_security.md` section 8). Missing env var or missing file aborts startup with a clear log line identifying the missing input. Sets the Sentry worker tag at startup (consistent with the Phase 1a pattern).

**Startup handshake with bounded retry.** The handshake distinguishes two failure classes that need different treatment:
- `MeshTerminalError` (e.g. 403 with populated errorCode) → abort immediately. Misconfiguration; the fail-fast invariant applies.
- `MeshTransientError` → retry in-process per `HANDSHAKE_RETRY_DELAYS_SECONDS`, then abort if still failing. The bound matters: the error classification maps a 403 with an *empty* errorCode (auth/clock skew) to transient, so bad credentials can present as transient — an unbounded retry would mask a credential error forever. With the bound, a genuine Spine blip is absorbed in-process (~8.5 minutes of patience), while persistent failure still aborts and surfaces via the process restart loop. `mesh_jobs` rows are durable throughout; nothing is lost, only delayed.

### 3.5 Modified Files

- `delivery_repository.py` — `create_job` gains an `is_fallback` keyword parameter (default `False`).
- `submission_repository.py` — new narrow `get_delivery_metadata` method (see 3.2).
- `mesh_repository.py` — new `list_orphaned_fallbacks()` query for the recovery sweep.
- `Dockerfile` — add `COPY mesh_worker_main.py ./` alongside the existing worker entry points; without it the dispatcher cannot run on Railway. A corresponding Railway service definition is a deployment action, noted in the Phase 5 checklist.
- `arch_submission.md` — document the dispatcher fallback ordering invariant, the recovery sweep, and the metadata-access deviation.

### 3.6 Tests

- `tests/test_mesh_payload.py` (new, unit): `RawPdfPayloadBuilder` passthrough behaviour.
- `tests/test_mesh_worker.py` (new, unit, mocked client and repos): success, transient-retry, transient-exhaustion, terminal-failure, fallback ordering, and sweep recovery paths.
- `tests/integration/test_mesh_worker_sandbox.py`: enqueue a `mesh_jobs` row, run one dispatch tick, assert the sandbox received the message and the row is `sent` (message_id stored verbatim). **This is a new hybrid test category**: it needs both Postgres and the sandbox, so unlike the Phase 2a DB-free convention it carries the `integration` marker, the `TEST_DATABASE_URL` guardrail, AND the `MESH_BASE_URL` module-level skip. Document the hybrid category in `docs/arch_testing.md` so the Phase 2a "one documented exception" rule does not silently erode.
- `tests/integration/test_mesh_worker_db.py` (DB-only, `MeshClient` mocked): terminal failure produces a `delivery_jobs` row with `is_fallback=TRUE` and correctly denormalised fields; a manufactured `fallback_triggered` orphan is recovered by one sweep pass, idempotently.

---

## Phase 4 — Tracking Poller and Deletion Job Rewrite

> **Planning gate:** Phase 4's detailed design must wait for the practice/NHS Digital answer on the workflow arrangement. If the outcome is GP Connect Send Document, the confirmation model gains ITK3 infrastructure/business acknowledgements delivered as inbound MESH messages (under the `_ACK` workflow IDs), which changes this phase substantially — tracking-endpoint polling alone would no longer be the whole story.

### 4.1 New File: `app/services/delivery/mesh_tracking_worker.py`

Polls `mesh_jobs` rows in status `sent` or `provider_accepted`. For each, calls `mesh_client.get_message_status(message_id=...)`.

Status transitions:
- Tracking shows `status == "Accepted"` AND `downloadTimestamp` populated → transition to `provider_accepted`, record `provider_accepted_at`.
- Tracking shows `status == "Acknowledged"` AND `statusSuccess == "SUCCESS"` → transition to `delivered`, record `delivered_at`.
- Tracking shows `status == "Error"` or `statusSuccess == "FAILED"` → transition to `failed`, record error. Sentry alert.
- Anything else → no transition. Re-poll on next tick.

Poll interval: starts at 5 minutes for `sent` rows, backs off to 30 minutes for `provider_accepted` rows. Configurable.

### 4.2 New File: `app/services/delivery/mesh_tracking_worker_main.py`

Entry point. Same fail-fast pattern.

### 4.3 Modify `deletion_job.py`

Existing deletion logic uses the `submission_delivery_status` VIEW (or its equivalent) to find submissions eligible for deletion. The VIEW logic changes:

- A submission is deletable when any of the following are true:
  - `delivery_jobs.status = 'sent'` and the submission was delivered via the email-only path (`MESH_DELIVERY=0` was active when this submission ran, or `is_fallback=FALSE`).
  - `mesh_jobs.status = 'delivered'`. This is the strong signal.
  - The submission was delivered via SMTP. Per the governing decision, SMTP-delivered submissions are not deletable automatically. The VIEW excludes them, and they accumulate for operator audit.

- A submission is NOT deletable while:
  - `mesh_jobs.status` is `pending`, `sent`, `provider_accepted`, or `failed` (the last because we may still want to retry or investigate).
  - `mesh_jobs.status = 'fallback_triggered'` and the matching `delivery_jobs` row hasn't reached `sent`.

Update the VIEW in a migration. The deletion job itself is unchanged in structure — only the eligibility logic changes.

> **To reconcile when Phase 4 is planned:** the statuses above need checking against the real `delivery_jobs` lifecycle. The Mailgun email path reaches `delivered` (via the webhook router), not `sent`; `sent` is the legacy SMTP path, which Known Limitation #9 in `arch_submission.md` says is *never* auto-deleted. So a MESH-to-Mailgun fallback row becomes deletable when its `delivery_jobs` row reaches `delivered`, and the "email-only path" bullet should key off `delivered`, not `sent`. Do not implement 4.3 as written without resolving this.

### 4.4 Tests

Unit and integration tests for the tracking worker covering each status transition. Integration tests for the new deletion eligibility logic via the VIEW.

---

## Phase 5 — Observability and Operator Tooling

### 5.1 Sentry Alert Routing

- `mesh_jobs.status = 'failed'` (terminal) → high-priority Sentry event with submission_id, mesh_job_id, message_id, last_error, last_error_code.
- `mesh_jobs.status = 'fallback_triggered'` → medium-priority event. Operator should know the practice received the form via email rather than MESH and may want to investigate the MESH issue.
- Tracking poller detects a `provider_accepted` row older than 24h → warning.
- Tracking poller detects a `provider_accepted` row older than 72h → error. Operator action required (call the practice).
- Dispatcher orphan sweep finds a `fallback_triggered` row without a matching `delivery_jobs` row → high-priority event.

Tags: `downstream_mode` (already set in Phase 1a), `mesh_status`, `practice_id`.

### 5.2 Operator SQL Scripts

Place in `scripts/operator/`:
- `mark_mesh_delivered.sql` — manually transition a stuck `provider_accepted` row to `delivered` after out-of-band confirmation.
- `find_duplicate_sends.sql` — given a submission_id or a date range, list all `mex_localid`s that map to MESH messages, to help investigate suspected duplicate sends.
- `reset_failed_mesh_job.sql` — reset a `failed` MESH job back to `pending` so the dispatcher retries.

Each script documents its usage in a comment header.

### 5.3 `deployment_checklist.md` Updates

Add a "MESH delivery" section to the deployment checklist:
- Confirm `MESH_DELIVERY` env var is set consistently across all processes.
- If `MESH_DELIVERY=1`: confirm all MESH env vars are populated (including `MESH_RECIPIENT_MAILBOX_ID`) and the certs are in place. Verify both `MESH_MAILBOX_ID` (sender) and `MESH_RECIPIENT_MAILBOX_ID` (destination) against the practice's MESH provisioning record — the two are easy to transpose, and a wrong recipient misroutes referrals silently (it does not bounce).
- Confirm the dispatcher and tracking worker processes are deployed.

---

## Summary of File Changes

### New Files (across all phases)

Phase 2a:
- `app/services/delivery/mesh/__init__.py`
- `app/services/delivery/mesh/client.py`
- `app/services/delivery/mesh/errors.py`
- `tests/test_mesh_client.py`
- `tests/test_mesh_client_integration.py`

Phase 2b:
- `app/services/delivery/mesh_enqueuer.py`
- `app/repositories/mesh_repository.py`
- `alembic/versions/0005_mesh_schema.py`
- `tests/test_mesh_enqueuer.py`
- `tests/integration/test_mesh_repository.py`
- `tests/integration/test_pdf_worker_mesh_path.py`

Phase 3:
- `app/services/delivery/mesh_payload.py`
- `app/services/delivery/mesh_worker.py`
- `mesh_worker_main.py`
- `mesh_constants.py`
- `tests/test_mesh_payload.py`
- `tests/test_mesh_worker.py`
- `tests/integration/test_mesh_worker_db.py`
- `tests/integration/test_mesh_worker_sandbox.py` (hybrid — see 3.6 for guardrail requirements)

Phase 4:
- `app/services/delivery/mesh_tracking_worker.py`
- `mesh_tracking_worker_main.py`
- `tests/test_mesh_tracking_worker.py`

Phase 5:
- `scripts/operator/*.sql`

### Modified Files

Phase 2b:
- `pdf_worker_main.py` — relax the `_validate_mesh_delivery()` abort so `MESH_DELIVERY=1` is accepted, and wire the downstream branch in `main()` (MESH path requires `MESH_RECIPIENT_MAILBOX_ID` and constructs `MeshEnqueuer`; email path unchanged). See 2b.4.
- `main.py` — remove the `MESH_DELIVERY=1` abort in `_validate_mesh_delivery()`; no mailbox check (the web tier does not deliver).
- `app/services/delivery/downstream_enqueuer.py` — docstring cleanup: the future implementation is `MeshEnqueuer`, not the obsolete `PdsEnqueuer` (cosmetic).
- `arch_submission.md` — add the MESH path to the pipeline diagram, document the new ordering invariant for the MESH path (`save_attachment → mesh_repo.create_job → mark_done` in the PDF worker; `mark_fallback_triggered → delivery_repo.create_job(is_fallback=True)` in the dispatcher).

Phase 3:
- `delivery_repository.py` — `create_job` gains an `is_fallback` parameter (default `False`).
- `submission_repository.py` — new narrow `get_delivery_metadata` method.
- `mesh_repository.py` — new `list_orphaned_fallbacks()` sweep query.
- `Dockerfile` — `COPY mesh_worker_main.py ./`.
- `arch_submission.md` — fallback ordering invariant, recovery sweep, metadata-access deviation.
- `docs/arch_testing.md` — document the hybrid (DB + sandbox) integration test category.

Phase 4:
- `deletion_job.py` — update eligibility logic.
- Migration: update the `submission_delivery_status` VIEW (or equivalent).
- `arch_submission.md` — retire Known Limitation #9 (SMTP retention) only if SMTP is genuinely no longer a deletion-blocking path. Otherwise leave it open.

Phase 5:
- `deployment_checklist.md`

---

## Open Items for Implementation Stage

These don't block planning but need answering during implementation:

1. ~~**MESH workflow ID for raw PDF sends.**~~ Superseded by the June 2026 research (see "Payload status: provisional" and `docs/nhs_integration_reference.md`): no registered workflow ID exists for raw PDF sends, so this is no longer an implementation detail to confirm — it is a production enablement gate (written workflow arrangement + endpoint lookup + verified first send). Phase 3 code is unblocked because `MESH_WORKFLOW_ID` is env-driven and the sandbox does not validate it.
2. ~~**MESH auth header exact format.**~~ Resolved by the Phase 1b sandbox investigation. Authoritative source for Phase 2a is `docs/nhs_integration_reference.md` ("Auth header construction"). If production behaviour diverges from the sandbox, the discrepancy goes into the integration reference and the client is amended.
3. **Tracking poll cadence.** Starts at 5 minutes per the plan, but practices' MESH clients poll their inboxes on widely different schedules (some 30s, some 30min). Worth measuring against the integration environment before locking the value.
4. ~~**Mailgun fallback content.**~~ Decided: identical email (same PDF, same subject, same body). No changes to `delivery_worker.py` or `delivery_service.py`. `is_fallback` is operational metadata only.
5. **`delivery_jobs.is_fallback=TRUE` downstream behaviour.** Per the decision in item 4, the delivery worker must do nothing different with fallback rows. Verify during Phase 3 implementation that nothing in the delivery path or webhook router routes on the new column (expected: nothing does — it is additive with a default).

---

## Confirmed by Sandbox Investigation

Carried forward from the prior planning round:

- MESH uses tracking-by-messageID, not receipt-based confirmation.
- 202 + `{"messageID": "..."}` response on successful send.
- `Mex-LocalID` round-trips but is not enumerable.
- Auth headers must be regenerated per request.
- Recipient acknowledgement is the authoritative delivery signal.
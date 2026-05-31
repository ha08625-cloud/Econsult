# MESH Integration Plan

## Document Status

This document supersedes a previous version that included a PDS lookup phase. PDS lookup has been removed from the plan entirely; the prior version is retrievable from git history if needed. The receiving GP practice is determined by deployment configuration (the practice owns the deployment that serves the form), not by patient-side lookup. The NHS number, when supplied by the patient, is treated as opaque data attached to the PDF for the GP's reference. It is not validated against PDS.

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
- **The receiving practice is determined by deployment configuration**, not by patient-side lookup. Each deployment serves exactly one practice. The destination MESH mailbox ID is therefore a property of `practices` (or the `app.state.practice_id`-backed config), loaded once at startup, and applied to every submission this process handles.
- **Delivery channel hierarchy:**
  1. **MESH** — primary delivery path when `MESH_DELIVERY=1`.
  2. **Mailgun HTTPS API** — secondary path. Used as fallback on terminal MESH failure.
  3. **SMTP** — break-glass legacy path only. Activated manually when both MESH and Mailgun are unavailable. Submissions delivered via SMTP are retained, not deleted, so operators can audit them once primary paths recover.
- The existing `pdf_worker.py` is unchanged in its core logic from Phase 1a. The polymorphic seam (`DownstreamEnqueuer`) gains a second implementation: `MeshEnqueuer`, which writes to `mesh_jobs` rather than `delivery_jobs`. The PDF worker itself remains downstream-agnostic.
- Sequential pipeline: Router → PDF → MESH (with Mailgun fallback on terminal MESH failure). No PDS hop. No FHIR build hop in the default plan (see "Deferred: FHIR/ITK3 envelope" below).
- All workers are separate processes for clarity and clean log separation.
- **Delivery confirmation requires recipient acknowledgement.** The tracking poller transitions `mesh_jobs.status` to `delivered` only when the tracking record shows `status == "Acknowledged" AND statusSuccess == "SUCCESS"`. Clinical referrals are not deleted until we have positive proof of recipient processing.

## Accepted Limitations

- **Duplicate-send on dispatcher crash.** If the dispatcher POSTs to Spine, Spine accepts (202), but the dispatcher crashes before committing the returned `message_id` to `mesh_jobs`, the next dispatcher run will resend the same submission. The GP practice receives two copies. This is documented and accepted. `Mex-LocalID` is still set per POST so an operator can manually correlate duplicates via the tracking endpoint when investigating.
- **Stuck-in-provider_accepted submissions.** If a GP practice's MESH client downloads but never acknowledges, the submission remains in `provider_accepted` indefinitely from our point of view. Detection is by elapsed-time alerting (24h warning, 72h error). Resolution is operator-driven: confirm out-of-band, then transition the row manually using the SQL script in Phase 5.

## Out of Scope (Explicitly Deferred)

These are intentionally not part of any phase in this document. Each is genuinely useful but separable, and deferring keeps the plan focused.

- **NHS Login.** Patient-side identity verification. If adopted later, an `assurance_level` column on `submission_records` may be needed to record verification confidence. That decision is deferred. The current schema is forward-compatible with adding such a column non-destructively.
- **GP Connect Send Document compliance.** The accreditation-gated future state in which our MESH messages carry an ITK3 FHIR envelope rather than a raw PDF. See "Deferred: FHIR/ITK3 envelope" below for the design implications when (if) we adopt it.
- **PDS lookup.** Removed for the reasons stated in the document status note: the destination is already known, so PDS lookup serves no routing purpose; using PDS for enrichment creates clinical-safety issues when patient-entered details and PDS records diverge.
- **NHS number client-side validation (Mod-11).** Worthwhile as a frontend UX improvement; tracked as a separate frontend ticket. Not part of this delivery plan.

### Deferred: FHIR/ITK3 envelope

The original plan included a FHIR Builder phase that wrapped the PDF in an ITK3 Bundle. The honest position:

- Raw MESH transport does not require any FHIR envelope. A MESH message can carry a binary PDF directly with appropriate workflow ID and MIME type headers. This is what the default plan below does.
- GP Connect Send Document compliance requires the PDF be embedded in an ITK3-conformant FHIR Message with `Task`, `DocumentReference`, and `Binary` resources, plus a specific MESH workflow ID (`GPFED_CONSULT_REPORT`). Adopting GP Connect compliance is a future, accreditation-gated decision.
- Therefore the FHIR Builder is not implemented in this plan. If GP Connect compliance is later adopted, a `MeshPayloadBuilder` interface is the right seam: the dispatcher's payload construction becomes pluggable, with implementations `RawPdfPayloadBuilder` (today) and `GpConnectSendDocumentPayloadBuilder` (later). Design Phase 3 with that seam in mind even though only the first implementation ships.

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
- Phase 2b adds migration 0005 (the `mesh_jobs` table and `delivery_jobs.is_fallback` column), the `MeshEnqueuer` adapter, the wiring in `pdf_worker_main.py` so `MESH_DELIVERY=1` no longer aborts startup, and the per-practice MESH mailbox configuration. After Phase 2b, the PDF worker can enqueue `mesh_jobs` rows but nothing consumes them yet.
- Phase 3 adds the dispatcher worker that consumes `mesh_jobs` and POSTs to MESH, including the Mailgun fallback when MESH terminally fails.
- Phase 4 adds the tracking poller (delivery confirmation) and rewrites `deletion_job.py` to be MESH-status-aware.
- Phase 5 covers Sentry alerts, operator SQL, and the deployment checklist.

Each phase is independently mergeable and reversible if needed.

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
| `MESH_MAILBOX_PASSWORD` | Input to the HMAC over the auth canonical string. |
| `MESH_SHARED_KEY` | HMAC secret. |
| `MESH_CA_CERT_PATH` | Path to CA bundle for verifying the server certificate. |
| `MESH_CLIENT_CERT_PATH` | Path to our client certificate. |
| `MESH_CLIENT_KEY_PATH` | Path to our client private key. |
| `MESH_WORKFLOW_ID` | Workflow ID for outgoing messages (introduced in Phase 3). |

### 1b.4 Parity limits

The nginx sidecar catches the most common mTLS mistakes: failing to present a cert, presenting one signed by the wrong CA, failing to verify the server cert against the expected CA. It does not catch Spine-specific quirks such as cipher-suite restrictions, peer-cert subject-DN validation, or revocation checks. First contact with NHS PTL may surface issues invisible to the local sandbox; this is an accepted limitation of any local mTLS emulation.

---

## Phase 2a — MESH Client Library

A pure code library: HTTP client for the MESH API, with auth-header construction, request signing, and parsing of the message-send and tracking responses. No DB schema, no worker process, no wiring.

### 2a.1 New File: `app/services/delivery/mesh/client.py`

Module exposing a `MeshClient` class. Constructor takes:
- `base_url` (string, e.g. `https://localhost:8700` for sandbox or the integration/production URL)
- `mailbox_id` (the sender mailbox ID — i.e. the practice's own MESH mailbox)
- `mailbox_password` (for auth header construction)
- `shared_key` (used in the HMAC over the auth string)
- `ca_cert_path`, `client_cert_path`, `client_key_path` — three mandatory string paths for mTLS. No `None`, no boolean toggle, no environment-based skip. See Phase 1b for the strategy. The constructor stores the paths but does not touch the filesystem; the worker entry point (Phase 3) owns the fail-fast `os.path.exists()` check.

Methods:
- `send_message(*, recipient_mailbox_id, payload_bytes, workflow_id, mex_localid, content_type) -> str` — POSTs to `/messageexchange/<mailbox_id>/outbox`. Returns the `messageID` from the 202 response. Raises `MeshTransientError` for retryable failures (network, 5xx, 503), `MeshTerminalError` for unrecoverable failures (4xx other than 503, malformed response).
- `get_message_status(*, message_id) -> dict` — GETs the tracking endpoint. Returns the parsed JSON. Raises the same exception types.
- `handshake() -> None` — performs the mandatory startup handshake (`POST /messageexchange/<mailbox>`). Called once per process at startup before any send.

Auth header generation is a private helper that constructs the canonical string `mailbox_id:nonce:nonce_count:password:timestamp` (or whatever the current MESH spec dictates — we have the sandbox to verify against), HMAC-SHA256s it with `shared_key`, and assembles the `Authorization: NHSMESH ...` value. The function is called per request because the timestamp is part of the input.

### 2a.2 New File: `app/services/delivery/mesh/errors.py`

```
class MeshError(Exception): ...
class MeshTransientError(MeshError): ...
class MeshTerminalError(MeshError): ...
```

The dispatcher (Phase 3) uses the exception type to decide retry vs fallback.

### 2a.3 New Files: `tests/test_mesh_client.py` and `tests/test_mesh_client_integration.py`

The test surface is split into two files matching the existing project convention (see `docs/arch_testing.md`):

**`tests/test_mesh_client.py` (unit tests, no marker, run in every CI build).** Mocks `requests.Session`. Covers:
- Auth header construction with a fixed timestamp and injected nonce (golden test).
- Session is constructed with `cert=(client_cert_path, client_key_path)` and `verify=ca_cert_path`.
- Error classification: network errors → transient, 5xx → transient, 403 with empty `errorCode` → transient (clock/auth retryable), 403 with populated `errorCode` → terminal, other 4xx → terminal, malformed 202 body → terminal.
- Successful 202 returns the 32-char hex `messageID` string. Storage type is `TEXT`, not UUID-parseable.

**`tests/test_mesh_client_integration.py` (marked `@pytest.mark.integration`, module-level skip on missing `MESH_BASE_URL`).** Runs against the local sandbox.

This is the first DB-free integration test in the project. It carries the integration marker so it stays out of the fast `make test` run and out of CI (the sandbox never runs in CI), but it does NOT carry the `TEST_DATABASE_URL` guardrail — it never touches Postgres. See the generalised "guard on the dependency you exercise" rule in `docs/arch_testing.md`.

Sandbox credentials are read from the canonical env vars (`MESH_MAILBOX_ID`, `MESH_MAILBOX_PASSWORD`, `MESH_SHARED_KEY`, `MESH_CA_CERT_PATH`, `MESH_CLIENT_CERT_PATH`, `MESH_CLIENT_KEY_PATH`) so the same `.env.sandbox` that runs the worker also runs this test. Only `MESH_BASE_URL` controls skip-vs-run; the rest are presence-required and fail loudly if absent (a developer who sets `MESH_BASE_URL` but forgets the cert paths should get a hard error, not a silent skip).

The recipient mailbox is hardcoded to `TARGET_MAILBOX` (the sandbox fixture in `sandbox/mailboxes.jsonl`).

Covers:
- Handshake against the sender mailbox returns 200.
- Send to `TARGET_MAILBOX` returns a 32-char hex `messageID`.
- Wrong shared key triggers `MeshTransientError` (matching the production "retry on auth failure" semantics — see error classification in 2a.1).
- `get_message_status` returns a dict with the expected fields.
- Non-existent client cert path → `MeshTransientError` (TLS handshake failure).

Integration tests are intentionally local-only. CI does not start the sandbox (see `sandbox/README.md`).

### 2a.4 No Wiring

Phase 2a deliberately does not wire the client into any worker. `pdf_worker_main.py` is unchanged. `MESH_DELIVERY=1` still refuses to start.

---

## Phase 2b — Schema, MeshEnqueuer, and Wiring

This phase makes `MESH_DELIVERY=1` a startable configuration. The PDF worker writes to `mesh_jobs` instead of `delivery_jobs`. Nothing consumes `mesh_jobs` yet; that is Phase 3.

### 2b.1 Migration `0005_mesh_schema.py`

(Renamed from `0005_mesh_fhir_schema` since the FHIR builder is no longer in scope.)

Creates the `mesh_jobs` table and adds `is_fallback` to `delivery_jobs`. Single transaction.

#### `mesh_jobs`

One row per MESH-enabled submission. Created by the PDF worker (via `MeshEnqueuer`). Consumed by the MESH dispatcher (Phase 3).

| Column | Type | Constraints |
|---|---|---|
| id | UUID | PRIMARY KEY DEFAULT gen_random_uuid() |
| submission_id | TEXT | NOT NULL UNIQUE REFERENCES submission_records(submission_id) |
| status | TEXT | NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'sent', 'provider_accepted', 'delivered', 'failed', 'fallback_triggered')) |
| message_id | TEXT | UNIQUE — set by dispatcher when MESH returns 202 |
| mex_localid | UUID | NOT NULL DEFAULT gen_random_uuid() — set on row creation for crash-trail correlation |
| recipient_mailbox_id | TEXT | NOT NULL — copied from practice config at enqueue time |
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

Note: `recipient_mailbox_id` is copied onto the row rather than re-resolved from practice config at dispatch time. This protects against a practice's MESH mailbox being reconfigured between enqueue and dispatch (rare, but cheap to defend against).

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
- `mark_failed(*, mesh_job_id, error, error_code, next_retry_after)` — increments `attempt_count`, records error fields.
- `mark_fallback_triggered(*, mesh_job_id)` — transitions to `fallback_triggered` when the dispatcher falls through to Mailgun.

### 2b.3 New File: `app/services/delivery/mesh_enqueuer.py`

Class `MeshEnqueuer` implementing the `DownstreamEnqueuer` Protocol from Phase 1a.

Constructor takes `mesh_repo: MeshRepository` and `recipient_mailbox_id: str`. The mailbox ID is resolved once at worker startup from practice config (see 2b.5) and passed in here.

`enqueue(submission_id)` calls `mesh_repo.create_job(submission_id=..., recipient_mailbox_id=self._recipient_mailbox_id)`. Returns `None`.

Note: `MeshEnqueuer` is a thinner adapter than `DeliveryEnqueuer` because the MESH path needs less information at this stage. No re-reads of `pdf_jobs` or `submission_records` — those happen in the dispatcher when it builds the MESH message.

### 2b.4 `pdf_worker_main.py` Wiring

Replace the current Phase 1a logic:
```python
if mesh_delivery == "1":
    logger.critical("MESH_DELIVERY=1 is not yet supported...")
    sys.exit(1)
```
with:
```python
if mesh_delivery == "1":
    recipient_mailbox_id = practice_repo.get_mesh_mailbox_id(app_state.practice_id)
    if recipient_mailbox_id is None:
        logger.critical(
            "MESH_DELIVERY=1 but practice %s has no MESH mailbox configured",
            app_state.practice_id,
        )
        sys.exit(1)
    downstream = MeshEnqueuer(
        mesh_repo=mesh_repo,
        recipient_mailbox_id=recipient_mailbox_id,
    )
    sentry_sdk.set_tag("downstream_mode", "mesh")
else:
    downstream = DeliveryEnqueuer(...)
    sentry_sdk.set_tag("downstream_mode", "email")
```

The same branch is added in `main.py._validate_startup` to assert the practice has a mailbox configured if `MESH_DELIVERY=1`. Fail-fast invariant.

### 2b.5 Practice Configuration Extension

`practices` table gains a `mesh_mailbox_id` column (nullable, since not every practice has MESH provisioned).

Migration: this is a separate migration (`0006_practice_mesh_mailbox.py`) to keep migration 0005 focused on the queue schema. The two migrations land together but as separate files.

`PracticeRepository` gains `get_mesh_mailbox_id(practice_id) -> str | None`.

The `AvailabilityEditor`/`PracticeSettingsTab` admin UI gains a "MESH Mailbox ID" field. Optional. Validated for shape (alphanumeric, NHS-mailbox-formatted) but not for actual existence — that is operator responsibility.

### 2b.6 Tests

- `tests/test_mesh_enqueuer.py` (new, unit tests, no DB). Same shape as `test_downstream_enqueuer.py`: mock the repo, assert forwarding.
- `tests/test_mesh_repository.py` (new, integration tests). Each method tested against a real DB.
- `tests/test_pipeline_repositories.py` updates: extend with `test_get_mesh_mailbox_id_*` tests.
- `tests/integration/` updates: a "PDF worker writes to mesh_jobs when MESH_DELIVERY=1" test that exercises the full PDF-worker-through-`MeshEnqueuer` flow with a real DB and no dispatcher.

---

## Phase 3 — MESH Dispatcher + Mailgun Fallback

Adds the dispatcher worker that consumes `mesh_jobs` and POSTs to MESH. Includes the fallback to Mailgun on terminal MESH failure.

### 3.1 New File: `app/services/delivery/mesh_worker.py`

Background worker loop. Claims one `mesh_jobs` row per iteration. Reads the attachment from `submission_attachments`. Reads minimal submission metadata (`condition_label`, `submitted_at`) from `submission_records`. Reads `delivery_email` from `pdf_jobs` (needed for the Mailgun fallback path).

Operation sequence per claim:
1. Build the MESH payload. With the FHIR builder deferred, this is the raw PDF bytes with content type `application/pdf` and a workflow ID configured per deployment (e.g. `REFERRAL_LETTER` or whatever the practice's MESH config dictates — see Open Items).
2. `mesh_client.send_message(...)` with `mex_localid = mesh_job.mex_localid` for idempotency correlation.
3. On 202: `mesh_repo.mark_sent(mesh_job_id, message_id)`. Job loop continues.
4. On `MeshTransientError`: `mesh_repo.mark_failed(...)` with `next_retry_after = now + backoff`. Job loop continues. The same job will be reclaimed when backoff expires.
5. On `MeshTerminalError`, or after `MAX_MESH_ATTEMPTS` transient failures: `mesh_repo.mark_fallback_triggered(...)`, then call `delivery_repo.create_job(...)` with `is_fallback=True` to enqueue the email path. The delivery worker (existing) then sends via Mailgun. Sentry alert fires (Phase 5).

The ordering invariant `mark_fallback_triggered` → `delivery_repo.create_job(is_fallback=True)` is critical. If the worker crashes between them, the next loop iteration will see `status='fallback_triggered'` but no `delivery_jobs` row. A small "find orphaned fallbacks" sweep (similar to the existing PDF worker orphan detection) handles this. Document the invariant and the recovery path in `arch_submission.md`.

### 3.2 New File: `mesh_worker_main.py`

Entry point. Validates env vars including `MESH_BASE_URL`, `MESH_MAILBOX_ID`, `MESH_MAILBOX_PASSWORD`, `MESH_SHARED_KEY`, `MESH_CA_CERT_PATH`, `MESH_CLIENT_CERT_PATH`, `MESH_CLIENT_KEY_PATH`, `MESH_WORKFLOW_ID`. For each of the three cert paths, validates the file exists on disk via `os.path.exists` before instantiating `MeshClient` — fail-fast invariant per `docs/arch_security.md` section 8. Missing env var or missing file aborts startup with a clear log line identifying the missing input. Instantiates `MeshClient`, performs the startup handshake, then runs the worker loop. Fail-fast on missing config, missing cert file, or handshake failure.

### 3.3 Startup Handshake

Per the sandbox investigation, the first interaction with a mailbox must be a handshake POST to `/messageexchange/<mailbox_id>`. Failing the handshake at startup is the right place to catch credential errors, mailbox misconfiguration, and connectivity issues — long before the first patient submission.

### 3.4 Tests

- Unit tests of `mesh_worker.py` with mocked `mesh_client` and repos, covering the success, transient-retry, terminal-failure, and fallback paths.
- Integration test against the sandbox: enqueue a `mesh_jobs` row, run one dispatch tick, assert the sandbox received the message and the row is `sent`.
- A "fallback triggers delivery_jobs row" integration test that uses a sandbox-simulated terminal failure (or a `MeshClient` mocked to raise `MeshTerminalError`) and asserts the email path picks it up.

---

## Phase 4 — Tracking Poller and Deletion Job Rewrite

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
- If `MESH_DELIVERY=1`: confirm all MESH env vars are populated, the practice's mailbox ID is in `practices.mesh_mailbox_id`, and the certs are in place.
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
- `migrations/0005_mesh_schema.py`
- `migrations/0006_practice_mesh_mailbox.py`
- `tests/test_mesh_enqueuer.py`
- `tests/test_mesh_repository.py`

Phase 3:
- `app/services/delivery/mesh_worker.py`
- `mesh_worker_main.py`
- `tests/test_mesh_worker.py`

Phase 4:
- `app/services/delivery/mesh_tracking_worker.py`
- `mesh_tracking_worker_main.py`
- `tests/test_mesh_tracking_worker.py`

Phase 5:
- `scripts/operator/*.sql`

### Modified Files

Phase 2b:
- `pdf_worker_main.py` — replace the "MESH_DELIVERY=1 not yet supported" abort with the wiring described in 2b.4.
- `main.py` — extend `_validate_mesh_delivery` to require a configured mailbox when `MESH_DELIVERY=1`.
- `practice_repository.py` — add `get_mesh_mailbox_id`.
- `frontend_admin-ui_src_screens_PracticeSettingsTab.tsx` — add MESH Mailbox ID field.
- `arch_submission.md` — add the MESH path to the pipeline diagram, document the new ordering invariant for the MESH path (`save_attachment → mesh_repo.create_job → mark_done` in the PDF worker; `mark_fallback_triggered → delivery_repo.create_job(is_fallback=True)` in the dispatcher).

Phase 3:
- `delivery_repository.py` — `create_job` gains an `is_fallback` parameter (default `False`).
- `arch_submission.md` — document the dispatcher fallback ordering invariant.

Phase 4:
- `deletion_job.py` — update eligibility logic.
- Migration: update the `submission_delivery_status` VIEW (or equivalent).
- `arch_submission.md` — retire Known Limitation #9 (SMTP retention) only if SMTP is genuinely no longer a deletion-blocking path. Otherwise leave it open.

Phase 5:
- `deployment_checklist.md`

---

## Open Items for Implementation Stage

These don't block planning but need answering during implementation:

1. **MESH workflow ID for raw PDF sends.** GP Connect uses `GPFED_CONSULT_REPORT`. For a non-GP-Connect raw-PDF send, the workflow ID is practice-and-use-case specific. Worth confirming with whichever practice goes first what their MESH client expects.
2. ~~**MESH auth header exact format.**~~ Resolved by the Phase 1b sandbox investigation. Authoritative source for Phase 2a is `docs/nhs_integration_reference.md` ("Auth header construction"). If production behaviour diverges from the sandbox, the discrepancy goes into the integration reference and the client is amended.
3. **Tracking poll cadence.** Starts at 5 minutes per the plan, but practices' MESH clients poll their inboxes on widely different schedules (some 30s, some 30min). Worth measuring against the integration environment before locking the value.
4. **Mailgun fallback content.** When MESH fails and we fall through to email, do we send the same PDF with the same subject line? Probably yes, but the email body should ideally mention that this is a fallback delivery so the practice doesn't think both channels are independent. Decide before Phase 3 ships.
5. **`delivery_jobs.is_fallback=TRUE` downstream behaviour.** Does the existing delivery worker do anything different with fallback rows? Probably not — same email, same body. But worth a defensive check in case anything routes on it.

---

## Confirmed by Sandbox Investigation

Carried forward from the prior planning round:

- MESH uses tracking-by-messageID, not receipt-based confirmation.
- 202 + `{"messageID": "..."}` response on successful send.
- `Mex-LocalID` round-trips but is not enumerable.
- Auth headers must be regenerated per request.
- Recipient acknowledgement is the authoritative delivery signal.

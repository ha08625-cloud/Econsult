# MESH/FHIR Integration Plan

## Governing Decisions

- MESH delivery is controlled by a single process-level env var `MESH_DELIVERY` (`0` or `1`). Single-practice, single-tenancy deployment for the foreseeable future.
- `MESH_DELIVERY` is read once at worker startup in `pdf_worker_main.py` and `main.py`. It is never re-read inside hot loops. A misconfigured deployment (e.g. PDF worker started with `MESH_DELIVERY=1` but MESH workers not deployed) MUST fail at startup, not silently degrade.
- **Delivery channel hierarchy:**
  1. **MESH** — primary delivery path when `MESH_DELIVERY=1`.
  2. **Mailgun HTTPS API** — secondary path. Used as fallback on terminal MESH failure.
  3. **SMTP** — break-glass legacy path only. Activated manually when both MESH and Mailgun are unavailable. Submissions delivered via SMTP are now **retained, not deleted**, so that operators can audit them once primary paths recover.
- PDS lookup is mandatory but routinely returns benign non-matches (e.g. middle name entered as second forename). PDS mismatch is treated identically to `spine_unavailable` for routing purposes — both result in `pds_status` recorded accordingly and submission proceeds (fail-open).
- Dual-failed submissions (both MESH and Mailgun fallback exhausted) are retained indefinitely. Recovery is via Sentry alert and operator intervention.
- The existing `pdf_worker.py` is modified to forward to a polymorphic downstream enqueuer chosen at startup. The worker itself remains pure — it does not know whether it is feeding the email path or the MESH path.
- The new flow is strictly sequential: Router → PDF → PDS → FHIR → MESH (with Mailgun as fallback on terminal MESH failure). Sequential is preferred over parallel for simplicity. Implication: when Spine is down, the PDF is still generated promptly, but MESH dispatch is delayed by the PDS retry window. The Mailgun fallback path also inherits this delay because it is only enqueued on terminal MESH failure, which happens downstream of PDS.
- All 5 new workers are separate processes for clarity and clean log separation. The memory overhead is acceptable at single-practice scale.
- **Duplicate-send risk is accepted.** MESH does not deduplicate on `Mex-LocalID`. A network timeout after Spine has accepted the POST will cause a duplicate send on retry. The duplicate is handled at the inbox-poller stage (see Phase 4) via idempotency on terminal status.

---

## Phase Sequencing

Phase 0 is being executed first. All other phases are deferred until the sandbox is running locally.

```
Phase 0 (sandbox) → Phase 1 (adapter refactor) → Phase 2 (PDS worker)
                 → Phase 3 (FHIR builder) → Phase 4 (MESH dispatcher)
                 → Phase 5 (inbox poller + deletion) → Phase 6 (observability)
```

- Phase 1 is a pure refactor: it changes the PDF worker's step 3 name and indirection but does **not** change runtime behaviour when `MESH_DELIVERY=0`. It can be merged on its own and validated in staging before Phase 2 begins.
- Phase 2 can be developed in parallel with Phase 0, since PDS uses a separate Spine endpoint (not MESH itself) and can be tested against mocked HTTP.
- Phase 4 and Phase 5 strictly require Phase 0 (the sandbox).

---

## New Tables (Full Schema)

All new tables — plus a modification to `delivery_jobs` and a new VIEW — are created in a single migration `0005_mesh_fhir_schema.py`. The migration must include `CREATE EXTENSION IF NOT EXISTS pgcrypto` if `gen_random_uuid()` is not already in use elsewhere in the schema.

### `pds_jobs`

One row per MESH-enabled submission. Created by the PDF worker (when `MESH_DELIVERY=1`). Claimed by the PDS lookup worker.

| Column | Type | Constraints |
|---|---|---|
| id | UUID | PRIMARY KEY DEFAULT gen_random_uuid() |
| submission_id | TEXT | NOT NULL UNIQUE REFERENCES submission_records(submission_id) |
| status | TEXT | NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'done', 'failed')) |
| attempt_count | INTEGER | NOT NULL DEFAULT 0 |
| last_error | TEXT | |
| next_retry_after | TIMESTAMPTZ | |
| created_at | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |
| updated_at | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |

Index: `(status, next_retry_after)` — supports the SKIP LOCKED claim query.

### `pds_traces`

Append-only PDS trace records. Written by the PDS lookup worker after a Spine call resolves (or fail-open occurs after retry exhaustion). Under normal operation the worker writes exactly one row per submission. The UNIQUE constraint on `submission_id` is omitted to allow future operator-driven re-traces without schema migration.

| Column | Type | Constraints |
|---|---|---|
| id | UUID | PRIMARY KEY DEFAULT gen_random_uuid() |
| submission_id | TEXT | NOT NULL REFERENCES submission_records(submission_id) |
| nhs_number | TEXT | (nullable — may be absent when pds_status = 'spine_unavailable') |
| pds_status | TEXT | NOT NULL CHECK (pds_status IN ('verified', 'not_found', 'mismatch', 'spine_unavailable')) |
| traced_at | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |

Index: `(submission_id, traced_at DESC)`.

**Note on re-traces:** Re-traces have no effect on already-dispatched MESH messages; they are diagnostic only. The FHIR builder reads "most recent trace by `traced_at`" but only does so once, when its job is claimed.

### `fhir_jobs`

One row per MESH-enabled submission. Created by the PDS lookup worker after PDS resolution (regardless of trace outcome — fail-open). Claimed by the FHIR builder.

| Column | Type | Constraints |
|---|---|---|
| id | UUID | PRIMARY KEY DEFAULT gen_random_uuid() |
| submission_id | TEXT | NOT NULL UNIQUE REFERENCES submission_records(submission_id) |
| status | TEXT | NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'done', 'failed')) |
| attempt_count | INTEGER | NOT NULL DEFAULT 0 |
| last_error | TEXT | |
| next_retry_after | TIMESTAMPTZ | |
| created_at | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |
| updated_at | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |

Index: `(status, next_retry_after)`.

### `submission_fhir_payloads`

One row per MESH-enabled submission. Written by the FHIR builder. The `payload_json` field stores a valid FHIR ITK3 Bundle with the DocumentReference `data` field set to `null` (not a placeholder string). PDF bytes are injected by the MESH dispatcher at transmit time.

| Column | Type | Constraints |
|---|---|---|
| id | UUID | PRIMARY KEY DEFAULT gen_random_uuid() |
| submission_id | TEXT | NOT NULL UNIQUE REFERENCES submission_records(submission_id) |
| payload_json | JSONB | NOT NULL |
| created_at | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |

### `mesh_jobs`

One row per MESH-enabled submission. Created by the FHIR builder. Claimed by the MESH dispatcher. Subsequently transitioned by the inbox poller.

| Column | Type | Constraints |
|---|---|---|
| id | UUID | PRIMARY KEY DEFAULT gen_random_uuid() |
| submission_id | TEXT | NOT NULL UNIQUE REFERENCES submission_records(submission_id) |
| status | TEXT | NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'provider_accepted', 'delivered', 'failed')) |
| message_id | TEXT | (populated by dispatcher on successful POST) |
| attempt_count | INTEGER | NOT NULL DEFAULT 0 |
| last_error | TEXT | |
| next_retry_after | TIMESTAMPTZ | |
| fallback_reason | TEXT | CHECK (fallback_reason IS NULL OR fallback_reason IN ('mesh_provider_failure', 'mesh_inbox_failure_receipt', 'mesh_dispatcher_exhausted')) |
| created_at | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |
| updated_at | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |

Indexes:
- `(status, next_retry_after)` — supports the SKIP LOCKED claim query.
- **`UNIQUE INDEX ON message_id WHERE message_id IS NOT NULL`** — supports inbox poller primary lookup and provides a database-level guard against race conditions where two receipts for the same message arrive simultaneously.

### `mesh_orphaned_receipts`

Local quarantine table for MESH receipts that cannot be matched to any known `mesh_jobs` row. Receipts are written here, a Sentry alert is fired, and then the receipt is deleted from the Spine MESH inbox to prevent inbox saturation.

| Column | Type | Constraints |
|---|---|---|
| id | UUID | PRIMARY KEY DEFAULT gen_random_uuid() |
| message_id | TEXT | NOT NULL UNIQUE — Spine's linked_message_id |
| local_id | TEXT | — Mex-LocalID from the receipt (if present) |
| raw_payload | TEXT | NOT NULL |
| created_at | TIMESTAMPTZ | NOT NULL DEFAULT NOW() |

`message_id` is UNIQUE so that retried polls do not create duplicate quarantine rows for the same orphaned receipt.

### `delivery_jobs` modification

Add one column:

| Column | Type | Constraints |
|---|---|---|
| is_fallback | BOOLEAN | NOT NULL DEFAULT FALSE |

Backfill is trivial: all existing rows are not fallbacks (the MESH path doesn't exist yet), so `DEFAULT FALSE` is correct.

### `submission_delivery_status` VIEW

Created in the same migration. Acts as a single source of truth for the choreographic outcome of each submission. Sentry alerting, the deletion job, and any future admin dashboards read from this view rather than re-deriving the compound logic.

```sql
CREATE VIEW submission_delivery_status AS
SELECT
    s.submission_id,
    CASE
        -- MESH path outcomes
        WHEN mj.status = 'delivered' THEN 'mesh_delivered'
        WHEN mj.status = 'failed' AND dj.is_fallback = TRUE AND dj.status = 'delivered' THEN 'fallback_delivered'
        WHEN mj.status = 'failed' AND dj.is_fallback = TRUE AND dj.status = 'sent' THEN 'fallback_sent_smtp'
        WHEN mj.status = 'failed' AND dj.is_fallback = TRUE AND dj.status = 'failed' THEN 'dual_failure'
        WHEN mj.status = 'failed' AND dj.is_fallback = TRUE AND dj.status = 'pending' THEN 'fallback_in_flight'
        WHEN mj.status IN ('pending', 'provider_accepted') THEN 'mesh_in_flight'

        -- Pure email path (MESH_DELIVERY=0)
        WHEN mj.status IS NULL AND dj.is_fallback = FALSE AND dj.status = 'delivered' THEN 'email_delivered'
        WHEN mj.status IS NULL AND dj.is_fallback = FALSE AND dj.status = 'sent' THEN 'email_sent_smtp'
        WHEN mj.status IS NULL AND dj.is_fallback = FALSE AND dj.status = 'failed' THEN 'email_failure'
        WHEN mj.status IS NULL AND dj.is_fallback = FALSE AND dj.status IN ('pending', 'provider_accepted') THEN 'email_in_flight'

        -- Upstream processing (PDF/PDS/FHIR phases)
        ELSE 'processing'
    END AS resolution_state
FROM submission_records s
LEFT JOIN mesh_jobs mj ON s.submission_id = mj.submission_id
LEFT JOIN delivery_jobs dj ON s.submission_id = dj.submission_id;
```

**Note on `_sent_smtp` states:** These exist as distinct categories because SMTP has no provider-side delivery confirmation. They are deliberately classified as *retain*, not delete, by the deletion job. See Phase 4.3.

---

## Phase 0 — MESH Sandbox (Prerequisite)

**This phase must be completed before Phases 4 and 5 are coded.** It can be set up in parallel with Phase 1.

### 0.1 Docker Compose

Create `docker-compose.yml` in the project root (or a dedicated `sandbox/` directory):

```yaml
services:
  mesh_sandbox:
    build:
      context: https://github.com/NHSDigital/mesh-sandbox.git#refs/tags/v1.0.4
    ports:
      - "8700:443"
    environment:
      - SHARED_KEY=TestKey
      - SSL=yes
      - STORE_MODE=file
      - MAILBOXES_DATA_DIR=/tmp/mesh/mailboxes
    volumes:
      - ./mailboxes.jsonl:/tmp/mesh/mailboxes/mailboxes.jsonl
    healthcheck:
      test: curl -ksf https://localhost/health || exit 1
      interval: 3s
      timeout: 10s
```

**Pre-flight check:** confirm `v1.0.4` is the current latest tag in the NHS Digital mesh-sandbox repository. If a newer tag exists, use it.

### 0.2 Mailboxes

Create `mailboxes.jsonl`:

```json
{"mailbox_id": "SENDER_MAILBOX", "mailbox_name": "My Sender System", "password": "password", "billing_entity": "Unknown", "ods_code": "X26", "org_code": "X26", "org_name": "Test Sender Org"}
{"mailbox_id": "TARGET_MAILBOX", "mailbox_name": "Target GP System", "password": "password", "billing_entity": "Unknown", "ods_code": "A99999", "org_code": "A99999", "org_name": "Test Target Org"}
```

### 0.3 Run and verify

```bash
docker compose up -d
curl -k https://localhost:8700/health
```

### 0.4 Local worker configuration

When running workers against the sandbox:
- `MESH_URL=https://localhost:8700`
- Mailbox ID: `SENDER_MAILBOX`, password: `password`, shared key: `TestKey`
- TLS verification disabled (`verify=False`) for the HTTP client. This must be conditional on `MESH_ENV=sandbox` (a new value, see Phase 1.5) so production deployments cannot accidentally disable TLS.

The sandbox automatically generates delivery receipts when a message is POSTed to `TARGET_MAILBOX`. This means the inbox poller (Phase 4) can be tested end-to-end against the sandbox immediately.

---

## Phase 1 — PDF Worker Adapter Refactor

This phase is a pure refactor. When `MESH_DELIVERY=0` (the only value in production at this stage), runtime behaviour is unchanged.

### 1.1 HTTP Router Change (`form_router.py`)

**Unchanged.** The form router continues to enqueue `pdf_jobs` as today. It has no knowledge of MESH, PDS, or any downstream branching.

### 1.2 New File: `downstream_enqueuer.py`

A thin module defining a uniform interface for what comes after PDF generation:

```python
class DownstreamEnqueuer(Protocol):
    def enqueue(
        self,
        *,
        submission_id: str,
        to_email: str,
        condition_label: str,
        submitted_at: datetime,
    ) -> None: ...

class DeliveryEnqueuer:
    def __init__(self, delivery_repo: DeliveryRepository): ...
    def enqueue(self, *, submission_id, to_email, condition_label, submitted_at):
        self._delivery_repo.create_job(
            submission_id=submission_id,
            to_email=to_email,
            condition_label=condition_label,
            submitted_at=submitted_at,
            is_fallback=False,
        )

class PdsEnqueuer:
    def __init__(self, pds_repo: PDSRepository): ...
    def enqueue(self, *, submission_id, to_email, condition_label, submitted_at):
        # MESH path needs only submission_id. The other arguments are ignored
        # because they live on submission_records / pdf_jobs already.
        self._pds_repo.create_job(submission_id=submission_id)
```

The PDF worker takes a `downstream: DownstreamEnqueuer` parameter and calls `downstream.enqueue(...)` blindly. Selection happens in `pdf_worker_main.py`.

### 1.3 `pdf_worker_main.py` wiring

```python
is_mesh = os.environ.get("MESH_DELIVERY") == "1"
if is_mesh:
    downstream = PdsEnqueuer(pds_repo=PDSRepository(conn))
else:
    downstream = DeliveryEnqueuer(delivery_repo=DeliveryRepository(conn))
pdf_worker.run_worker(..., downstream=downstream)
```

### 1.4 `pdf_worker.py` change

`_process_job` step 2 changes from:

```python
delivery_repo.create_job(submission_id=..., to_email=..., ...)
```

to:

```python
downstream.enqueue(submission_id=..., to_email=..., condition_label=..., submitted_at=...)
```

### 1.5 Ordering invariant — updated docstring

The ordering invariant in `pdf_worker.py` and `arch_submission.md` is updated to read:

1. `save_attachment` (UPSERT — safe on retry)
2. `downstream.enqueue` (idempotent — ON CONFLICT DO NOTHING in both repo implementations)
3. `pdf_repo.mark_done`

The docstring at the top of `pdf_worker.py` is updated to make explicit that `downstream.enqueue` must follow `save_attachment` because **downstream consumers** (the delivery worker on the email path, OR the FHIR builder via the PDS chain on the MESH path) rely on the attachment existing. The structural test `test_process_job_ordering_invariant` retains its existing assertion but its docstring is widened to match.

### 1.6 `delivery_jobs.is_fallback` column

Added in migration `0005_mesh_fhir_schema.py` even though it is logically a Phase 1a concern. Migration 0005 is a single transaction; splitting it would create awkward intermediate states.

`DeliveryRepository.create_job` gains an `is_fallback: bool = False` keyword argument. All existing callers pass `False` (or omit it, taking the default). The MESH dispatcher in Phase 3 passes `True` when enqueuing a fallback job.

### 1.7 Tests

- `test_pdf_worker.py`: existing tests stay, with `_make_delivery_repo()` replaced by a `MagicMock(spec=DownstreamEnqueuer)`. Add new test exercising the `PdsEnqueuer` adapter end-to-end (verifies `pds_repo.create_job` is called when the adapter is wired).
- New test file `test_downstream_enqueuer.py`: unit tests for both adapter implementations.
- All new tests carry `pytestmark = pytest.mark.integration` if they touch the DB; pure unit tests do not.

---

## Phase 2 — PDS Layer and Spine Key Management

### 2.1 New File: `pds_lookup_worker.py`

Claims `pds_jobs`. Performs Spine PDS lookup. Writes `pds_traces`. Enqueues `fhir_jobs` on completion (whether the trace was `verified`, `not_found`, `mismatch`, or `spine_unavailable` — all four proceed to FHIR build, which is fail-open).

#### Credential management (top-of-loop, before any DB claim)

In-memory state: `doppler_keys`, `doppler_expires_at`, `doppler_backoff_until`, `spine_token`, `spine_expires_at`, `spine_backoff_until`, `last_failed_key_hash`, `degraded_state_started_at`.

**Startup:** Synchronous Doppler fetch. On failure: `sys.exit(1)`. On success: populate `doppler_keys`, set `doppler_expires_at = now + 12 hours`.

**Per loop iteration, before claiming a job:**

**Step 1 — Doppler key refresh.** If `doppler_keys is None` OR `now >= doppler_expires_at`, and not in backoff, attempt fetch. On success:
- Compute `new_key_hash = sha256(private_key_string)`.
- If `new_key_hash == last_failed_key_hash`: discard the key, set `doppler_keys = None`, increment exponential backoff (5s → 10s → 20s → 60s cap), continue. Log warning.
- Otherwise: store keys, reset expiry to `now + 12 hours`, clear `last_failed_key_hash`.

On Doppler fetch failure: increment exponential backoff. Log warning. Retain existing `doppler_keys` if present.

**Step 2 — Spine token refresh.** If `now >= spine_expires_at` and not in backoff and `doppler_keys is not None`, sign JWT and POST to `/oauth2/token`.
- On 200: cache token, set `spine_expires_at = now + (expires_in - 30s)`. Clear `degraded_state_started_at`.
- On 401: extract `key_hash = sha256(doppler_keys.private_key)`. Set `last_failed_key_hash = key_hash`. Set `doppler_keys = None`, `spine_token = None`, `spine_expires_at = 0`, `doppler_expires_at = 0` (force re-fetch). Fire error-severity Sentry event. Begin exponential backoff cycle.
- On 5xx/timeout: set `spine_backoff_until = now + 1 minute`. Do not flag the key as dead.

**Step 3 — Degraded state alert.** If `doppler_keys is None` or `spine_token is None`:
- If `degraded_state_started_at is None`, set it to `now`.
- If `now - degraded_state_started_at > 5 minutes`, fire critical-severity Sentry event (rate-limited to one per 5 minutes).
- Sleep and continue. Do not claim a job.

#### Job processing

- **On 200 from PDS:** write `pds_traces` with status `verified` (or `mismatch` if demographics conflict). Enqueue `fhir_jobs`. Mark `pds_job` done.
- **On 404 from PDS:** write `pds_traces` with status `not_found`. Enqueue `fhir_jobs`. Mark done. (Fail-open.)
- **On 401 from PDS endpoint** (token expired mid-job):
  - Clear `spine_token = None`, set `spine_expires_at = 0`.
  - Release job to `pending` with `next_retry_after = now + 10s`.
  - **Do not increment `attempt_count`.** A 401 mid-job is a benign token-rotation event, not a job failure. The degraded-state alerting in the top-of-loop credential management already protects against persistent token bugs by halting job claims when credentials are unavailable.
  - Do not write `pds_traces` yet.
- **On 5xx/timeout:** standard retry with exponential backoff. After `MAX_PDS_ATTEMPTS` exhausted: write `pds_traces` with status `spine_unavailable`, enqueue `fhir_jobs`, mark done. (Fail-open.)

Retry constants: new file `pds_constants.py`, identical pattern to `pdf_constants.py`.

### 2.2 New File: `pds_worker_main.py`

Entry point for the PDS worker process. Same pattern as `pdf_worker_main.py`. Validates `MESH_DELIVERY=1` at startup and refuses to start if it is `0` (an inactive PDS worker should not be deployed; this is configuration drift).

### 2.3 Startup Guards (`main.py _validate_startup()`)

When `MESH_DELIVERY=1`, assert presence of:
- `DOPPLER_TOKEN`
- `MESH_ENV` (must be one of `sandbox`, `integration`, `production`)
- `SENDER_ODS_CODE`
- `TARGET_ODS_CODE`

When `MESH_ENV=sandbox` OR `MESH_ENV=integration`, assert that `TARGET_ODS_CODE` is in the hardcoded permitted-test set `{"X26"}`. Any other value → refuse to start.

When `MESH_ENV=production`, assert that `TARGET_ODS_CODE NOT IN {"X26"}`. This symmetric guard prevents the inverse misconfiguration: shipping clinical data to a test mailbox.

`MESH_DELIVERY` itself is asserted to be present and equal to `"0"` or `"1"` — no defaulting. Missing or malformed → refuse to start.

When `MESH_DELIVERY=0`, the MESH-specific env vars (above) should be absent. Their presence is logged as a warning at startup (configuration drift indicator) but does not abort.

The same `MESH_DELIVERY` validation is duplicated in every `*_worker_main.py`. The `deployment_checklist.md` mandates that all processes share the same value.

### 2.4 Migration `0005_mesh_fhir_schema.py`

Creates all six new tables, adds the `delivery_jobs.is_fallback` column, creates the `submission_delivery_status` VIEW, and creates the `pgcrypto` extension if not present. Single migration, single transaction.

---

## Phase 3 — FHIR Builder

### 3.1 New File: `fhir_builder_worker.py`

Claims `fhir_jobs`. Reads:
- `submission_attachments` (guaranteed to exist — the PDF worker wrote it before the PDS worker enqueued the PDS job, which in turn led to the FHIR job).
- `pds_traces` — most recent row by `traced_at` for the submission (guaranteed to exist — the PDS worker wrote it before enqueuing FHIR).

Builds the FHIR ITK3 Bundle as a Python dict. The `DocumentReference.content[0].attachment.data` field is set to `None`. PDF bytes are not yet base64-encoded — that happens in the MESH dispatcher to avoid storing the encoded form.

Writes the bundle to `submission_fhir_payloads`. Enqueues `mesh_jobs`. Marks `fhir_job` done.

ODS codes: read from environment (`SENDER_ODS_CODE`, `TARGET_ODS_CODE`). The startup guard has already asserted these are valid for the deployment's `MESH_ENV`. The builder does not re-validate.

### 3.2 New File: `fhir_worker_main.py`

Entry point for the FHIR builder process.

### 3.3 Test fixture

Add a canonical FHIR ITK3 bundle JSON file to `tests/fixtures/itk3_bundle_example.json`. Both the builder test (which constructs and validates structure) and the dispatcher test (Phase 3 — verifies PDF injection traversal) read from this fixture. Any future ITK3 schema change is then a single-fixture update with two tests forced to re-pass.

---

## Phase 4 — MESH Dispatcher

### 4.1 New File: `mesh_worker.py`

Claims `mesh_jobs`. Reads `payload_json` from `submission_fhir_payloads`. Reads PDF bytes from `submission_attachments`.

Base64-encodes the PDF in memory. Traverses the bundle dict to inject:

```python
bundle["entry"][N]["resource"]["content"][0]["attachment"]["data"] = base64_string
```

where `N` is the index of the DocumentReference entry. This traversal path must be tested explicitly with the fixture bundle from Phase 2.3 — it is structural and silently breakable.

Serialises via `json.dumps`. POSTs to MESH API.

#### Idempotency / duplicate-send handling

- Sets the `Mex-LocalID` header to `str(mesh_jobs.id)` on every POST. **MESH does not deduplicate on `Mex-LocalID`** — it is a diagnostic trace header only. The Mex-LocalID is used by the inbox poller (Phase 4) for crash recovery, not by Spine.
- A network timeout after Spine has accepted the POST will cause a duplicate send on retry. This is an accepted risk consistent with HTTP-without-two-phase-commit. The duplicate is handled cleanly at the inbox-poller stage (see Phase 4.1).

#### Success / failure

- **On success** (Spine returns `message_id`): atomically set `mesh_jobs.status = 'provider_accepted'` and `mesh_jobs.message_id = <returned_id>`. On a duplicate-send retry, this overwrites `message_id` with the *latest* accepted send's ID. That is acceptable because we track the submission, not individual MESH attempts.
- **On failure:** standard retry with exponential backoff. After `MAX_MESH_ATTEMPTS` exhausted: set `status = 'failed'`, set `fallback_reason = 'mesh_dispatcher_exhausted'`, enqueue `delivery_jobs` with `is_fallback=True`, fire Sentry.

#### MESH base URL resolution from `MESH_ENV`

- `sandbox` → `https://localhost:8700` (TLS verification disabled — only in this env)
- `integration` → `https://msg.int.spine2.ncrs.nhs.uk`
- `production` → `https://mesh-sync.national.ncrs.nhs.uk`

Retry constants: new file `mesh_constants.py`.

### 4.2 New File: `mesh_worker_main.py`

Entry point for the MESH dispatcher process.

---

## Phase 5 — Inbox Poller, Fallback, and Cleanup

### 5.1 New File: `mesh_inbox_worker.py`

Polls MESH inbox at interval `MESH_POLL_INTERVAL_SECONDS` (default 300).

#### Per-receipt processing

1. **Download and parse.** Extract `linked_message_id`, `receipt_status`, and `Mex-LocalID` from the receipt.

2. **Primary lookup.** Search `mesh_jobs WHERE message_id = linked_message_id`.

3. **Fallback lookup (crash recovery / duplicate send).** If primary lookup returns no row, attempt to parse `Mex-LocalID` as a UUID. The UUID parse is wrapped in `try/except` — a malformed `Mex-LocalID` does not crash the worker; it routes to the orphan path. If parsing succeeds, search `mesh_jobs WHERE id = <parsed_uuid>`.

4. **Resolution:**

   - **Found via primary (happy path):**
     - If status is already `delivered` or `failed`: skip DB update (idempotency guard). DELETE receipt from Spine.
     - Otherwise: transition `provider_accepted → delivered` or `provider_accepted → failed` based on `receipt_status`. On failure: set `fallback_reason = 'mesh_inbox_failure_receipt'`, enqueue `delivery_jobs` with `is_fallback=True`, fire Sentry. DELETE receipt from Spine.
   - **Found via fallback (crash recovery or duplicate-send):**
     - If status is already `delivered` or `failed`: this is the duplicate-send case (a second receipt for a message we already resolved). Skip DB update. DELETE receipt from Spine.
     - Otherwise: backfill `message_id = linked_message_id`, then apply the same status transition logic as the primary path. DELETE receipt from Spine.
   - **Not found via either (true orphan):** write the full receipt payload to `mesh_orphaned_receipts` (UNIQUE on `message_id` means a retried poll is a no-op). Fire error-severity Sentry alert ("Orphaned MESH receipt quarantined"). DELETE receipt from Spine.

5. **On 429/5xx from Spine:** exponential backoff before resuming standard poll interval.

#### Ordering of quarantine write versus Spine delete

For the orphan path specifically: write to `mesh_orphaned_receipts` and commit **before** deleting from Spine. If the Spine delete fails, the next poll re-reads the same receipt; the UNIQUE constraint on `message_id` makes the local write a no-op, and the Spine delete can be retried.

### 5.2 New File: `mesh_inbox_worker_main.py`

Entry point for the inbox poller process.

### 5.3 Modify `deletion_job.py`

Replace the two existing DELETE statements with a VIEW-driven eligibility selection:

```sql
WITH eligible AS (
    SELECT submission_id
    FROM submission_delivery_status
    WHERE resolution_state IN ('mesh_delivered', 'fallback_delivered', 'email_delivered')
)
DELETE FROM submission_photos WHERE submission_id IN (SELECT submission_id FROM eligible);
DELETE FROM submission_attachments WHERE submission_id IN (SELECT submission_id FROM eligible);
DELETE FROM submission_fhir_payloads WHERE submission_id IN (SELECT submission_id FROM eligible);
```

All three deletes run in the same implicit transaction (single connection, no explicit COMMIT between).

#### Deletion truth table (must be covered by integration tests)

| Scenario | VIEW `resolution_state` | Action |
|---|---|---|
| MESH primary success | `mesh_delivered` | Delete |
| Mailgun fallback after MESH failure | `fallback_delivered` | Delete |
| Pure Mailgun path (MESH_DELIVERY=0) | `email_delivered` | Delete |
| **SMTP fallback after MESH+Mailgun failure** | `fallback_sent_smtp` | **Retain** |
| **Pure SMTP path (MESH_DELIVERY=0, break-glass)** | `email_sent_smtp` | **Retain** |
| Dual failure | `dual_failure` | Retain |
| MESH in flight | `mesh_in_flight`, `fallback_in_flight` | Retain |
| Pure email in flight | `email_in_flight` | Retain |
| Upstream processing (PDF/PDS/FHIR not yet complete) | `processing` | Retain |

**SMTP retention rationale:** SMTP has no provider-side delivery confirmation. We retain submissions delivered via SMTP indefinitely so that operators can audit them after primary delivery paths recover. Manual deletion is the cleanup mechanism. This resolves the previously-documented `arch_submission.md` limitation #9 by making the retention behaviour intentional rather than accidental.

`arch_submission.md` limitation #10 (`provider_accepted` with no Mailgun webhook) is **not** resolved by this plan; it remains a known hole in the Mailgun-without-webhook path and is unchanged.

#### Test fixture helper

`make_submission_with_jobs(db, mj_status=..., dj_status=..., dj_is_fallback=...)` is added to `conftest.py` (or `admin_test_helpers.py`) so each scenario above can be expressed as a one-line setup. Integration tests must exercise every row of the truth table.

---

## Phase 6 — Observability and Operator Tooling

### 6.1 Sentry alert routing

Document in `arch_security.md` (new MESH/PDS section) the alert severity and routing policy:
- Doppler fetch failure (transient): warning, not paged.
- Spine 401 with new key (key-rotation failure): error, paged during business hours.
- Degraded state >5 minutes: critical, paged immediately.
- MESH dispatcher exhausted: error, paged during business hours.
- MESH delivery failed via receipt: error, paged during business hours.
- Orphaned MESH receipt: error, paged during business hours.
- Dual failure: critical, paged immediately.

Confirm routing with the operator before going live.

### 6.2 Operator SQL scripts

Add a `/scripts/` directory containing:

- `find_dual_failures.sql` — `SELECT submission_id FROM submission_delivery_status WHERE resolution_state = 'dual_failure';`
- `find_stuck_in_flight.sql` — submissions in any `*_in_flight` state for more than 24 hours.
- `find_orphaned_receipts.sql` — recent rows from `mesh_orphaned_receipts`.
- `mass_reroute_mesh_to_email.sql` — break-glass script that takes a list of submission_ids, marks their MESH-side jobs as `failed` with `fallback_reason = 'operator_initiated'`, and enqueues fallback `delivery_jobs`. This is documented in `deployment_checklist.md` and is the operator's tool for catastrophic MESH outages.

These scripts are documentation, not infrastructure. They live in the repo as plain `.sql` files and are run by operators against the production database via Railway's database console or `psql`.

### 6.3 `deployment_checklist.md` updates

- All worker processes must share the same `MESH_DELIVERY` value.
- All worker processes must share the same `MESH_ENV` value.
- The MESH-to-email rerouting script is documented and tested in staging before any production deployment.

---

## Summary of File Changes

### New files

| File | Purpose |
|---|---|
| `pds_constants.py` | PDS retry thresholds |
| `pds_repository.py` | Owns `pds_jobs` and `pds_traces` |
| `pds_lookup_worker.py` | PDS lookup loop |
| `pds_worker_main.py` | PDS worker entry point |
| `downstream_enqueuer.py` | Adapter protocol and two implementations |
| `fhir_repository.py` | Owns `fhir_jobs` and `submission_fhir_payloads` |
| `fhir_builder_worker.py` | FHIR ITK3 bundle builder loop |
| `fhir_worker_main.py` | FHIR builder entry point |
| `mesh_constants.py` | MESH retry thresholds |
| `mesh_repository.py` | Owns `mesh_jobs` and `mesh_orphaned_receipts` |
| `mesh_worker.py` | MESH dispatcher loop |
| `mesh_worker_main.py` | MESH dispatcher entry point |
| `mesh_inbox_worker.py` | Inbox poller loop |
| `mesh_inbox_worker_main.py` | Inbox poller entry point |
| `0005_mesh_fhir_schema.py` | Migration: 6 new tables, `delivery_jobs.is_fallback`, `submission_delivery_status` VIEW |
| `tests/fixtures/itk3_bundle_example.json` | Canonical FHIR bundle fixture |
| `scripts/find_dual_failures.sql` | Operator query |
| `scripts/find_stuck_in_flight.sql` | Operator query |
| `scripts/find_orphaned_receipts.sql` | Operator query |
| `scripts/mass_reroute_mesh_to_email.sql` | Break-glass rerouting |
| `docker-compose.yml` | MESH sandbox |
| `mailboxes.jsonl` | Sandbox mailboxes |

### Modified files

| File | Change |
|---|---|
| `pdf_worker.py` | Step 2 renamed: `delivery_repo.create_job` → `downstream.enqueue`; docstring widened to cover both delivery and MESH consumers |
| `pdf_worker_main.py` | Wire `DeliveryEnqueuer` or `PdsEnqueuer` based on `MESH_DELIVERY` |
| `delivery_repository.py` | `create_job` accepts `is_fallback: bool = False` |
| `main.py` | `_validate_startup()` extended for MESH env vars, symmetric ODS check (sandbox/integration force `X26`, production forbids `X26`) |
| `deletion_job.py` | VIEW-driven eligibility; three deletes including `submission_fhir_payloads` |
| `arch_submission.md` | Update pipeline diagram and ordering invariant; retire limitation #9; clarify limitation #10 is unchanged |
| `arch_security.md` | Add MESH/PDS sections (Spine auth, key rotation handling, orphan quarantine, Sentry routing) |
| `architecture.md` | Add MESH/FHIR capability index entry |
| `file_structure.md` | Register new files |
| `railway.toml` | Register 5 new worker services |
| `ci.yml` | Pytest discovery is already marker-based per project conventions; no change required unless new test directories are added outside the default discovery path |
| `deployment_checklist.md` | MESH_DELIVERY/MESH_ENV coherence rules, break-glass procedures |

---

## What is Explicitly Deferred

- Multi-tenancy / per-practice MESH configuration.
- Merging worker processes to reduce Railway service count.
- NHS sandbox credentials (PTL) — integration testing blocked until these arrive; `MESH_ENV=integration` path is built but untestable until then.
- Structured PTL "auto-reject mailbox" test suite — design now, execute when credentials arrive.
- MESH chunking strategy for submissions exceeding the per-message size limit. Current scope assumes payloads will fit. Revisit if photo counts or sizes increase.
- Operator runbook for dual-failed submissions (Sentry alert exists; the human response to that alert is not yet specified beyond the SQL scripts in Phase 5.2).
- **Programmatic** MESH-to-email rerouting (admin endpoint or CLI). The SQL script in Phase 5.2 is the interim mechanism; a proper admin tool is deferred.

---

## Open Caveats Confirmed at Plan Stage

These were confirmed during planning:

- `DeliveryRepository.create_job` signature is being extended with `is_fallback: bool = False`. The adapter is updated in lockstep. Future signature changes must update both.
- MESH does **not** deduplicate on `Mex-LocalID`. Duplicate-send risk on network timeouts is accepted; duplicate receipts are handled idempotently in the inbox poller.
- The FHIR ITK3 DocumentReference traversal path will be tested against a canonical fixture bundle. Any structural change to the bundle is caught by failing tests in both the builder and the dispatcher.
- Sentry alert routing/severity policy is specified in Phase 6.1 and must be confirmed with the operator before go-live.
- Doppler is the chosen secret manager. Team has a paid plan with adequate SLA for the planned thresholds.
- `v1.0.4` of the NHS Digital mesh-sandbox is the assumed tag; confirm latest before Phase 0 execution.

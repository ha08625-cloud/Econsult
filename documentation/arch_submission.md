# Submission, Serialization & Delivery

**LLM INSTRUCTIONS:** This document covers design decisions and strict boundaries for the submission domain. Read the actual source files for function signatures, field names, and schema details.

---

## Scope

Finalizing forms, persisting submission records, auditing, PDF generation, attachment storage, and delivering clinical output to the practice. Includes delivery retry orchestration.

**Key files:** `serialisation.py`, `serialisation_contracts.py`, `submission_repository.py`, `attachment_repository.py`, `delivery_service.py`, `delivery_orchestration.py`, `delivery_constants.py`, `delivery_events.py`, `app/utils/pdf_formatter.py`

---

## Submission Lifecycle — Critical Invariants

- A `submission_record` MUST be created in the database with `delivery_status = "pending"` **before** any delivery is attempted. This ensures the record exists even if the process crashes during delivery.
- The PDF stored in `submission_attachments` is the **canonical delivery artifact**. It is generated once at submission time and must never be regenerated. Whatever was in the PDF at submission time is what gets sent on every delivery attempt, including retries. This is correct clinical behaviour — the submission is immutable from the moment the patient clicks submit.
- `condition_label` is stored denormalised on `submission_records` for lightweight access during delivery without loading `clinical_output_json`. If a condition label is later changed in the ruleset, historical records retain the label that was active when the patient submitted. This is intentional — it preserves the clinical context at submission time.
- Delivery failures are **operational, not clinical**. They are never surfaced to the patient. The patient always receives a submission ID regardless of delivery outcome.
- `delivery_email` is captured from the practice record **at submission time** and stored in the submission record. Historical audits reflect the actual address used even if the practice email is later changed.
- `delivery_attempts` counts recorded outcomes, not physical SMTP connections. A crash during a send leaves the count un-incremented. The true number of SMTP connections for a given submission may exceed `delivery_attempts`.

---

## Delivery Retry

### Retry Schedule

Defined in `delivery_constants.py`. The backoff schedule is `[1, 10, 60]` minutes, giving `MAX_ATTEMPTS = 4` (first attempt + 3 retries). Total retry window is 71 minutes. This is deliberately short for clinical safety — if delivery cannot succeed within this window, alternative delivery mechanisms (deferred, separate ticket) take over.

`MAX_ATTEMPTS` is derived from the schedule length. It is the single canonical expression of the exhaustion threshold. No other module may define its own maximum.

| Event | delivery_attempts before | delivery_attempts after | next_retry_after set to |
|---|---|---|---|
| First attempt (router) | 0 | 1 | On failure: NOW() + 1 min |
| Retry 1 (worker) | 1 | 2 | On failure: NOW() + 10 min |
| Retry 2 (worker) | 2 | 3 | On failure: NOW() + 60 min |
| Retry 3 (worker) | 3 | 4 | Not set (exhausted) |
| Exhaustion guard | 4 | not incremented | not set |

### Orchestration (`delivery_orchestration.py`)

`attempt_delivery` is the single entry point for all delivery attempts — both the first attempt from the router and retries from the (deferred) background worker. It enforces all delivery policy:

Guards (checked in order before any send or increment):
1. Already sent — returns immediately if `delivery_status == "sent"`.
2. Exhaustion — returns immediately if `delivery_attempts >= MAX_ATTEMPTS`. Logs at CRITICAL.
3. Too early — returns immediately if `next_retry_after is not None and next_retry_after > now_utc`.

The guards mean the worker can call `attempt_delivery` on any submission without re-implementing policy checks. No increment occurs for any guard return.

`DeliveryOutcomeStatus` is an enum with five values: `SENT`, `FAILED`, `ALREADY_SENT`, `EXHAUSTED`, `TOO_EARLY`. `DeliveryOutcome` is a dataclass carrying `status`, `attempts`, `next_retry_after`, and `error`.

`PendingDelivery` is a dataclass in `submission_repository.py` carrying only the fields the orchestration layer needs. `get_pending_delivery` returns this instead of a raw dict.

**Backoff index calculation:** On `EmailDeliveryError`, `next_retry_after` is computed before calling `record_attempt_outcome`, using `pending.delivery_attempts + 1` as the expected post-increment count (`backoff_index = post_increment_count - 1`). This allows exactly one call to `record_attempt_outcome` per attempt. The `RETURNING delivery_attempts` value is used as `actual_count` in the `DeliveryOutcome` to confirm the database count matches expectations, and guards against a potential future TOCTOU race where `pending.delivery_attempts` could be stale.

**Concurrency (TOCTOU):** Two races exist in `attempt_delivery`. First, the already-sent guard reads `delivery_status` from `get_pending_delivery`; concurrent calls could both pass this guard before either completes. Second, `pending.delivery_attempts` used for backoff index calculation is a pre-read value — the `RETURNING` clause on `record_attempt_outcome` provides the authoritative post-increment count but does not prevent both concurrent calls from reading the same pre-increment value. In single-process operation neither race is exploitable. Once a background worker is added, row-level locking (`SELECT ... FOR UPDATE`) or an atomic compare-and-swap is required. This is a documented requirement for the worker ticket.

### Exhaustion Policy

`exhausted` is never stored in the database. A submission is a clinical record — its status reflects delivery outcome: `pending`, `sent`, or `failed`. Exhaustion is a delivery policy outcome, not a property of the submission. When automatic retries are exhausted, the submission remains `failed` in the database. The orchestration layer detects exhaustion by comparing `delivery_attempts` against `MAX_ATTEMPTS`. `VALID_STATUSES` does not change.

### Retryable Query (`list_retryable`)

`SubmissionRepository.list_retryable(limit=50)` returns `PendingDelivery` objects for submissions where `delivery_status = 'failed' AND next_retry_after IS NOT NULL AND next_retry_after <= NOW()`, ordered by `submitted_at ASC`.

Uses `delivery_status = 'failed'` (not `NOT IN ('sent')`) so that pending submissions with anomalous `next_retry_after` values are left for operator investigation rather than silently retried. The `limit` parameter prevents a single sweep from attempting an unbounded number of failed submissions. The background worker is expected to call `list_retryable` in a loop until it returns empty or hits its own time budget.

### Manual Recovery SQL

```sql
-- Reset a single exhausted submission for manual retry.
-- Verify the submission_id and inspect delivery_error before running.
-- Verify the attachment still exists in submission_attachments.
UPDATE submission_records
SET delivery_attempts = 0,
    next_retry_after  = NOW(),
    delivery_status   = 'failed',
    delivery_error    = 'Manual reset for retry'
WHERE submission_id = '<SUBMISSION_ID>'
  AND delivery_status = 'failed'
  AND delivery_attempts >= 4;
```

Setting `delivery_attempts = 0` gives a full set of retries. Setting it higher (e.g. 3) gives fewer. `next_retry_after = NOW()` makes it immediately eligible.

---

## Design Decisions

### Output Contracts (`serialisation_contracts.py`)

There are two output types, each with a distinct purpose:

- **`ClinicalOutput`** — lossy by design. Strips provenance and encoder internals. Safe for clinical and patient use. Contains `question_labels` (answer_key -> question text at submission time) so the record is self-contained and interpretable without reloading the ruleset. Also carries `contact_preferences` — these are stored here so the clinical record is self-contained and the delivery service receives everything it needs in a single argument.
- **`AuditOutput`** — lossless. Contains full `runtime_state` snapshot, safety evaluation, and ruleset version. Intended for debugging, safety review, and regulatory inspection.

Neither contract may be used as an input back into the engine. This module contains no logic.

### Serialisation (`serialisation.py`)

- Produces `ClientStateView` (for frontend rendering), `ClinicalOutput`, and `AuditOutput`.
- Serialisation **never mutates state**.
- `condition_label` is passed in explicitly by the calling layer. This module never accesses presentation metadata from the ruleset directly.

### Submission Repository (`submission_repository.py`)

- Owns the `submission_records` table.
- `delivery_status` values: `"pending"`, `"sent"`, `"failed"`.
- `condition_label` is stored alongside the submission record at creation time.
- `attachment_count` is stored as an audit field recording how many photos were submitted. It is not used by the delivery or retry layers. The parameter is required (no default) on `create_submission` so a future call site cannot accidentally omit it and silently write 0.
- `create_submission` uses named `%(name)s` parameters rather than positional `%s` placeholders. This makes the column-to-value mapping explicit in the source and prevents silent data corruption if columns are reordered.
- `get_submission` and `list_by_status` use an explicit `_SUBMISSION_COLUMNS` constant rather than `SELECT *`. This constant must be updated when migrations add or remove columns.
- `record_attempt_outcome` is the sole post-attempt write path. It performs a single atomic UPDATE with `RETURNING delivery_attempts`.
- `list_retryable(limit=50)` returns `PendingDelivery` objects. It does not return `submission_id` — the orchestration layer does not need it, and excluding it keeps the projection minimal.
- Must never: send emails, import engine modules, or make retry decisions.

### Attachment Repository (`attachment_repository.py`)

- Owns the `submission_attachments` table.
- Stores pre-rendered PDF bytes in a separate table from `submission_records` so that queries against submission records never load blob data. This separation matters now that photo bytes are embedded in the PDF — a single submission can be 20 MB or more (5 photos at 5 MB each produces a combined PDF in that range). This blob is loaded fully into memory on every delivery attempt, including retries. Acceptable at current traffic scale.
- `save_attachment(submission_id, pdf_bytes)` — inserts. Raises on duplicate (exactly-once invariant).
- `get_attachment(submission_id)` — returns raw bytes. Raises `AttachmentNotFound` if absent. A missing attachment at retry time is always an error — the submission was created in a broken state.
- `delete_attachment(submission_id)` — deletes. Idempotent.
- Must never: generate or modify PDFs, send emails, or make retry decisions.

### Delivery Service (`delivery_service.py`)

The delivery service is an abstract base class (`DeliveryService`) with two concrete implementations selected at startup by `main.py` based on `DEV_MODE`:

- **`EmailDeliveryService`** — production implementation. Reads SMTP configuration from environment variables **at instantiation time** (`__init__`), not at send time. This means a misconfigured deployment fails immediately at startup rather than silently at the moment of the first submission.
- **`ConsoleDeliveryService`** — development only. Logs the full email payload to stdout. Raises `RuntimeError` at instantiation if `DEV_MODE` is not set, preventing accidental use in production.

`send_clinical_output` accepts `to_email`, `condition_label`, `pdf_bytes`, `submission_id`, and `submitted_at`. The delivery service has no knowledge of clinical contracts — `ClinicalOutput` is not part of its interface. The email body is a static message containing only submission metadata (submission ID, condition label, timestamp). All clinical detail is carried exclusively in the PDF attachment.

`EmailDeliveryError` is raised on any SMTP failure. The calling layer (the orchestration module) catches it, records the failure, and computes the retry schedule.

The delivery service must never: access the database, update delivery status, import engine modules, generate PDFs, or retry on failure.

### Delivery Events (`delivery_events.py`)

Four string constants for structured logging of the delivery lifecycle: `DELIVERY_SENT`, `DELIVERY_FAILED`, `DELIVERY_EXHAUSTED`, `DELIVERY_RETRY_TOO_EARLY`. No application-module dependencies.

### PDF Formatter (`app/utils/pdf_formatter.py`)

- Pure function `generate_pdf()` — takes `ClinicalOutput`, metadata, optional `practice_name`, and optional `photo_bytes`; returns raw PDF bytes.
- No database access, no imports from routers or delivery service.
- Called by `form_router.py` at submission time. The returned bytes are stored in `submission_attachments` and sent as-is on every delivery attempt (including retries). The PDF is never regenerated.
- `practice_name` is injected into the router via `get_practice_name` dependency and passed directly to `generate_pdf`. The name is captured once at startup. If the practice name is changed via the admin interface, PDFs will show the old name until the next server restart — this is a known and accepted limitation.
- `photo_bytes=None` and `photo_bytes=[]` both produce a PDF with no photos section. A non-empty list appends a PHOTOS section after the footer.

### Known Limitations on MIME Validation

Server-side MIME validation for photo uploads relies on the HTTP `Content-Type` header supplied by the browser. This header is not cryptographically verified and can be spoofed. No magic bytes validation (checking actual file header bytes) is performed anywhere in the system — client-side MIME type checking in `EditScreen` is a usability guard against accidental misuse, not a security control. Server-side magic bytes checking is deferred.

---

## Known Limitations

1. A process crash after a successful send but before `record_attempt_outcome` completes results in a duplicate delivery on retry. This is the accepted tradeoff: duplicate delivery is safer than silently exhausting retries without a successful send.
2. `delivery_attempts` counts recorded outcomes, not physical SMTP connections. A crash during the send leaves the count un-incremented.
3. Attachments are not deleted on successful delivery. Storage cost for PDFs is trivial. A cleanup job is deferred until the background worker exists.
4. `ConsoleDeliveryService` in dev mode exercises the retry path but never produces a real `EmailDeliveryError` unless deliberately stubbed.
5. Orphan detection (pending submissions with `delivery_attempts = 0` older than 5 minutes) currently runs only at startup. An orphan created after startup is invisible until the next deploy. Periodic orphan checking is desired and should be implemented when the background worker arrives.
6. Manual recovery from an exhausted submission requires direct database access.
7. Systemic failures (e.g. expired SMTP credentials) cause submissions to accumulate. `list_retryable` processes them in batches. Each timed-out submission incurs the full SMTP timeout (~30s). The worker ticket must address timeout and concurrency strategy.
8. `attempt_delivery` has two TOCTOU races: the already-sent guard (concurrent calls could both pass before either completes) and the backoff index calculation (both calls could read the same pre-increment `delivery_attempts` value). Neither is exploitable in single-process operation. The worker ticket must implement row-level locking or atomic compare-and-swap to close both gaps.
9. CRITICAL-level logging is the sole alerting mechanism. Structured error reporting should be revisited when the background worker is added.
10. Alternative delivery backup and admin portal notification for delivery failures are planned as a separate ticket, before collecting real patient data.
11. The stored PDF may be 20 MB or more for photo-heavy submissions (5 photos at 5 MB each). This is loaded fully into memory on each delivery attempt, including retries. Acceptable at current traffic scale but should be reviewed before significant volume.

---

## Startup Validation (enforced in `main.py`)

These conditions abort startup rather than silently degrade:

- `PRACTICE_ID` env var not set
- Database contains more than one practice
- `PRACTICE_ID` does not match any practice in the database
- Practice has no email address
- SMTP env vars not set in production mode

At startup, `main.py` also queries for orphan submissions (`delivery_status = 'pending'`, `delivery_attempts = 0`, `submitted_at` older than 5 minutes) and emits a CRITICAL-level log if any are found.

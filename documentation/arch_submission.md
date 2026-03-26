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

Guards (checked in order before any send):
1. Already sent — returns immediately if `delivery_status == "sent"`.
2. Exhaustion — returns immediately if `delivery_attempts >= MAX_ATTEMPTS`. Logs at CRITICAL.
3. Too early — returns immediately if `next_retry_after > now_utc`.

The guards mean the worker can call `attempt_delivery` on any submission without re-implementing policy checks.

`DeliveryOutcomeStatus` is an enum with five values: `SENT`, `FAILED`, `ALREADY_SENT`, `EXHAUSTED`, `TOO_EARLY`. `DeliveryOutcome` is a dataclass carrying `status`, `attempts`, `next_retry_after`, and `error`.

`PendingDelivery` is a dataclass in `submission_repository.py` carrying only the fields the orchestration layer needs. `get_pending_delivery` returns this instead of a raw dict.

`record_attempt_outcome` uses `RETURNING delivery_attempts` to return the actual new count from the database. The orchestration layer uses this returned value for backoff index calculation, avoiding a TOCTOU race between the read in `get_pending_delivery` and the atomic increment in the UPDATE.

### Exhaustion Policy

`exhausted` is never stored in the database. A submission is a clinical record — its status reflects delivery outcome: `pending`, `sent`, or `failed`. Exhaustion is a delivery policy outcome, not a property of the submission. When automatic retries are exhausted, the submission remains `failed` in the database. The orchestration layer detects exhaustion by comparing `delivery_attempts` against `MAX_ATTEMPTS`. `VALID_STATUSES` does not change.

### Retryable Query (`list_retryable`)

Returns submissions where `next_retry_after IS NOT NULL AND next_retry_after <= NOW() AND delivery_status = 'failed'`, ordered by `submitted_at ASC`, limited by a `limit` parameter (default 50).

Uses `delivery_status = 'failed'` (not `NOT IN ('sent')`) so that pending submissions with anomalous `next_retry_after` values are left for operator investigation rather than silently retried.

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
- `record_attempt_outcome` is the sole post-attempt write path. It performs a single atomic UPDATE with `RETURNING delivery_attempts`.
- Must never: send emails, import engine modules, or make retry decisions.

### Attachment Repository (`attachment_repository.py`)

- Owns the `submission_attachments` table.
- Stores pre-rendered PDF bytes in a separate table from `submission_records` so that queries against submission records never load blob data. This separation is important once photo attachments are added, where a single submission could be 25MB+.
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

- Pure function `generate_pdf()` — takes `ClinicalOutput`, metadata, and optional `practice_name`; returns raw PDF bytes.
- No database access, no imports from routers or delivery service.
- Called by `form_router.py` at submission time. The returned bytes are stored in `submission_attachments` and sent as-is on every delivery attempt (including retries). The PDF is never regenerated.
- `practice_name` is injected into the router via `get_practice_name` dependency and passed directly to `generate_pdf`. The name is captured once at startup. If the practice name is changed via the admin interface, PDFs will show the old name until the next server restart — this is a known and accepted limitation.

---

## Known Limitations

1. A process crash after a successful send but before `record_attempt_outcome` completes results in a duplicate delivery on retry. This is the accepted tradeoff: duplicate delivery is safer than silently exhausting retries without a successful send.
2. `delivery_attempts` counts recorded outcomes, not physical SMTP connections. A crash during the send leaves the count un-incremented.
3. Attachments are not deleted on successful delivery. Storage cost for PDFs is trivial. A cleanup job is deferred until the background worker exists.
4. `ConsoleDeliveryService` in dev mode exercises the retry path but never produces a real `EmailDeliveryError` unless deliberately stubbed.
5. Orphan detection (pending submissions with `delivery_attempts = 0` older than 5 minutes) currently runs only at startup. An orphan created after startup is invisible until the next deploy. Periodic orphan checking is desired and should be implemented when the background worker arrives.
6. Manual recovery from an exhausted submission requires direct database access.
7. Systemic failures (e.g. expired SMTP credentials) cause submissions to accumulate. `list_retryable` processes them in batches. Each timed-out submission incurs the full SMTP timeout (~30s). The worker ticket must address timeout and concurrency strategy.
8. The already-sent guard in `attempt_delivery` has a TOCTOU window. The `RETURNING` clause on `record_attempt_outcome` closes the data race on the count, but concurrent calls could still both pass the already-sent guard. The worker ticket must implement row-level locking or atomic compare-and-swap to close this gap.
9. CRITICAL-level logging is the sole alerting mechanism. Structured error reporting should be revisited when the background worker is added.
10. Alternative delivery backup and admin portal notification for delivery failures are planned as a separate ticket, before collecting real patient data.

---

## Startup Validation (enforced in `main.py`)

These conditions abort startup rather than silently degrade:

- `PRACTICE_ID` env var not set
- Database contains more than one practice
- `PRACTICE_ID` does not match any practice in the database
- Practice has no email address
- SMTP env vars not set in production mode

At startup, `main.py` also queries for orphan submissions (`delivery_status = 'pending'`, `delivery_attempts = 0`, `submitted_at` older than 5 minutes) and emits a CRITICAL-level log if any are found.
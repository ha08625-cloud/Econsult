# Submission, Serialization & Delivery

**LLM INSTRUCTIONS:** This document covers design decisions and strict boundaries for the submission domain. Read the actual source files for function signatures, field names, and schema details.

---

## Scope

Finalizing forms, persisting submission records, auditing, photo storage, PDF generation, attachment storage, and delivering clinical output to the practice via a three-stage async pipeline.

**Key files (Commit 1, fully deployed):** `serialisation.py`, `serialisation_contracts.py`, `submission_repository.py`, `attachment_repository.py`, `delivery_service.py`, `delivery_orchestration.py`, `delivery_constants.py`, `delivery_events.py`, `pdf_formatter.py`, `pdf_repository.py`, `delivery_repository.py`, `pdf_constants.py`

**Key files (Commit 2, not yet deployed):** `pdf_worker.py`, `pdf_worker_main.py`, `photo_repository.py`, `delivery_worker.py` (rewritten), `deletion_job.py`

---

## Pipeline Architecture

The system uses a three-stage async pipeline. The web request persists the submission and raw photos, the PDF worker generates the PDF and enqueues delivery, and the delivery worker sends the email. Each stage owns its own table and communicates only via job creation.

```
HTTP request (form_router.py)
  -> submission_records (create)
  -> submission_photos (save raw photos)       [Commit 2]
  -> pdf_jobs (enqueue)

PDF worker (pdf_worker.py)                     [Commit 2]
  -> submission_photos (read)
  -> submission_attachments (UPSERT pdf bytes)
  -> delivery_jobs (enqueue)
  -> pdf_jobs (mark done)

Delivery worker (delivery_worker.py)
  -> delivery_jobs (claim)
  -> submission_attachments (read pdf bytes)
  -> SMTP send
  -> delivery_jobs (mark sent/failed)

Deletion cron (deletion_job.py)               [Commit 2]
  -> submission_photos (delete where sent)
  -> submission_attachments (delete where sent)
```

**Until Commit 2 is deployed**, the system continues to run entirely on the old synchronous path: `form_router.py` generates the PDF inline, writes to `submission_attachments`, and calls `attempt_delivery` directly. The `pdf_jobs` and `delivery_jobs` tables exist in the schema but are empty and unused.

---

## Submission Lifecycle Invariants

- A `submission_records` row MUST be created before any child rows (`submission_photos`, `pdf_jobs`). It is the FK target for all downstream tables.
- The PDF stored in `submission_attachments` is the canonical delivery artifact. It is generated once by the PDF worker and sent as-is on every delivery attempt, including retries. The submission is immutable from the moment the patient clicks submit.
- `condition_label` is stored denormalised on `submission_records` at submission time. Historical records retain the label that was active when the patient submitted, even if the ruleset is later updated.
- Delivery failures are operational, not clinical. They are never surfaced to the patient. The patient always receives a submission ID regardless of delivery outcome.
- `delivery_email` is captured at submission time and stored on `pdf_jobs.delivery_email`. After Commit 2, it does not appear on `submission_records`. Historical audits reflect the actual address used even if the practice email is later changed.

---

## Ordering Invariant (PDF Worker)

**This invariant must never be broken by future changes.**

Within the PDF worker, operations on a single job execute in this order:

1. `save_attachment` (UPSERT — safe on retry)
2. `delivery_repo.create_job` (ON CONFLICT DO NOTHING — idempotent)
3. `pdf_repo.mark_done`

A `delivery_jobs` row can only exist after `save_attachment` has completed successfully. This guarantees the delivery worker will always find an attachment when it claims a delivery job. There is no need to handle a missing attachment as a normal case in the delivery worker — if the attachment is absent, the invariant has been broken and the error should propagate loudly.

**Crash recovery at each step:**

| Crash point | State | Recovery |
|---|---|---|
| Before `save_attachment` | No attachment, no delivery job | PDF worker retries; regenerates PDF from stored photos |
| After `save_attachment`, before `create_job` | Attachment exists, no delivery job | UPSERT is safe; worker creates delivery job then marks done |
| After `create_job`, before `mark_done` | Attachment and delivery job both exist | Both UPSERT and DO NOTHING fire safely; worker marks done |
| After `mark_done` | Job is done; not re-claimed | No action needed |

There is no crash point that leaves the system in an irrecoverable state without operator intervention.

---

## Job Tables

### `pdf_jobs`

One row per submission. Created by `form_router.py` immediately after saving photos. Polled by the PDF worker.

Status values: `pending`, `done`, `failed`.

`attachment_count` and `delivery_email` are captured at job creation time by the form router. This makes the PDF worker immune to Migration D (which drops those columns from `submission_records`) — the worker reads them from the job row, not from `submission_records`.

`status` remains `pending` throughout all retries until `mark_done` succeeds or `MAX_PDF_ATTEMPTS` is exhausted (at which point it becomes `failed` permanently).

### `delivery_jobs`

One row per submission. Created by the PDF worker as the second-to-last step of processing. Polled by the delivery worker.

Status values: `pending`, `sent`, `failed`.

`to_email`, `condition_label`, and `submitted_at` are denormalised at creation time so the delivery worker never needs to read `submission_records`.

The `submission_id` column has a UNIQUE constraint. `create_job` uses ON CONFLICT DO NOTHING, making it safe to call multiple times for the same submission without inserting a duplicate. This is the mechanism that ensures PDF worker retries do not create duplicate delivery jobs.

---

## Job Claiming (SKIP LOCKED)

Both `PDFRepository.claim_next_pending` and `DeliveryRepository.claim_next_pending` use `SELECT ... FOR UPDATE SKIP LOCKED`. The lock is held only for the duration of the claim transaction, which immediately sets `next_retry_after` to 10 minutes in the future. This moves the job outside the eligible window before the lock is released, preventing a second worker from claiming the same job without requiring a `status = processing` column or a long-held lock.

---

## Retry Schedule

### PDF jobs (`pdf_constants.py`)

`MAX_PDF_ATTEMPTS = 3`. Backoff: `[5, 10]` minutes. After 3 failures the job is marked `failed` permanently.

### Delivery jobs (`delivery_constants.py`)

`MAX_ATTEMPTS = 4` (derived from `len(RETRY_BACKOFF_MINUTES) + 1`). Backoff: `[1, 10, 60]` minutes. Total retry window: 71 minutes. This is deliberately short for clinical safety.

---

## Orphan Detection

### PDF worker orphan detection

`PDFRepository.list_orphaned_submissions(older_than_minutes)` uses a LEFT JOIN between `submission_records` and `pdf_jobs` to find submissions that have no corresponding PDF job and are older than the threshold:

```sql
SELECT sr.submission_id
FROM submission_records sr
LEFT JOIN pdf_jobs pj ON sr.submission_id = pj.submission_id
WHERE pj.submission_id IS NULL
  AND sr.submitted_at < NOW() - INTERVAL '1 minute' * %(threshold)s
```

This catches the case where `form_router.py` crashed after `create_submission` but before `pdf_repo.create_job`. No mutation is performed — the PDF worker logs at CRITICAL (rate-limited to once per 60 seconds) and continues. Recovery requires operator intervention.

**Manual recovery:** Inspect whether `submission_photos` rows exist for the orphaned submission. If photos are present and the count matches `attachment_count` on the pdf_jobs row, an operator can manually insert a `pdf_jobs` row. If photos are missing or incomplete, the submission is unrecoverable via automation and must be communicated to the practice for re-collection.

### Pre-Commit-2 orphan detection (delivery worker)

Until Commit 2, the delivery worker calls `SubmissionRepository.list_orphans` (checking `delivery_status = 'pending'` with zero attempts) and logs at CRITICAL. This is replaced by the PDF worker's LEFT JOIN orphan detection after Commit 2.

---

## Photo Retention

Raw photos (`submission_photos`) and generated PDFs (`submission_attachments`) are deleted by a nightly Railway cron job (`deletion_job.py`) for submissions where `delivery_jobs.status = 'sent'`. The cron runs at midnight.

- Minimum retention: ~5.25 hours (submission at 6:45pm grace window close, deletion at midnight).
- Maximum retention: ~24 hours (submission at practice open, deletion next midnight).

`pdf_jobs` and `delivery_jobs` rows are never deleted. They accumulate as an operational audit trail. Storage cost is trivial (no blobs). A periodic cleanup can be added later if needed.

The long-term clinical record is `clinical_output_json` and `audit_output_json` on `submission_records`, which contain no photos.

---

## Defensive Photo Count Check (PDF Worker)

After claiming a PDF job, the PDF worker compares `len(photos)` from `photo_repository.get_photos` against `job.attachment_count` (stored on the `pdf_jobs` row at creation time). If they do not match, the job is failed immediately without generating a PDF or creating a delivery job. This is a safety net against partial photo persistence caused by a router crash mid-save, and is separate from orphan detection.

---

## Pillow Header Validation

The form router runs `Image.open(...).verify()` on each uploaded photo before any database write. `verify()` checks the file header only, not the full decode. A file with a valid header but a truncated body will pass this check but will cause the PDF worker to fail during PDF generation. In that case the PDF worker retries and eventually marks the job as `failed`. The submission record exists, the failure is logged, and operator intervention can determine whether the photos are recoverable. This is an accepted limitation.

---

## Design Decisions

### Output Contracts (`serialisation_contracts.py`)

Two output types with distinct purposes:

- **`ClinicalOutput`** — lossy by design. Strips provenance and encoder internals. Safe for clinical and patient use. Contains `question_labels` (answer_key -> question text at submission time) so the record is self-contained and interpretable without reloading the ruleset.
- **`AuditOutput`** — lossless. Contains full `runtime_state` snapshot, safety evaluation, and ruleset version. Intended for debugging, safety review, and regulatory inspection.

Neither contract may be used as an input back into the engine. This module contains no logic.

### Serialisation (`serialisation.py`)

- Produces `ClientStateView` (for frontend rendering), `ClinicalOutput`, and `AuditOutput`.
- Serialisation never mutates state.
- `condition_label` is passed in explicitly by the calling layer. This module never accesses presentation metadata from the ruleset directly.

### Submission Repository (`submission_repository.py`)

Owns the `submission_records` table. After Commit 1, this module is responsible only for `create_submission` and `get_submission`. Delivery status tracking, retry queries, and orphan detection have moved to `DeliveryRepository` and `PDFRepository`.

`_SUBMISSION_COLUMNS` is an explicit column list used in all SELECT queries. Never use `SELECT *`. This constant must be updated when migrations add or remove columns. After Migration D (Commit 2), the delivery columns (`delivery_status`, `delivery_email`, etc.) are removed from both the table and this constant.

`create_submission` uses named `%(name)s` parameters rather than positional `%s` placeholders to make the column-to-value mapping explicit.

### Attachment Repository (`attachment_repository.py`)

Owns the `submission_attachments` table. After Commit 2, `save_attachment` becomes an UPSERT (`ON CONFLICT (submission_id) DO UPDATE SET pdf_bytes = EXCLUDED.pdf_bytes`) to support safe PDF worker retries. Until Commit 2 it raises on duplicate (exactly-once invariant on the old path).

`get_attachment` raises `AttachmentNotFound` if absent. A missing attachment at delivery time is always an error — the ordering invariant guarantees it cannot happen under normal operation.

Attachments are stored as BYTEA in Postgres. At current scale (~5 photos/day, nightly cleanup) this is acceptable. If the system scales to multiple practices with high photo volume, BYTEA storage will cause WAL bloat, expensive vacuuming, and slow backups. Migrate to object storage (S3/equivalent) at that point.

### Delivery Service (`delivery_service.py`)

Abstract base class (`DeliveryService`) with two concrete implementations:

- **`EmailDeliveryService`** — production. SMTP configuration read from environment variables at instantiation time (not at send time), so a misconfigured deployment fails at startup rather than at the first submission.
- **`ConsoleDeliveryService`** — development only. Raises `RuntimeError` at instantiation if `DEV_MODE` is not set.

`send_clinical_output` accepts `to_email`, `condition_label`, `pdf_bytes`, `submission_id`, and `submitted_at`. The delivery service has no knowledge of clinical contracts. The email body is a static message; all clinical detail is carried exclusively in the PDF attachment.

Must never: access the database, update delivery status, import engine modules, generate PDFs, or retry on failure.

---

## Known Limitations

1. **Duplicate delivery on crash.** A process crash after a successful SMTP send but before `mark_sent` results in a re-send on the next retry. Duplicate delivery is safer than silently dropping a submission.
2. **Pillow `verify()` is header-only.** A file with a valid header but truncated body passes upload validation but causes PDF generation failure. The PDF worker retries and eventually marks the job as failed. The failure is visible to operators.
3. **No health check or liveness probe for workers.** Railway process restart is the only recovery mechanism for a stuck worker. Explicitly deferred. Revisit before scaling to multiple practices.
4. **Orphan submissions require operator intervention.** If the router crashes between `create_submission` and `pdf_repo.create_job`, the orphan detection query finds the submission but automation cannot determine whether photos were fully saved. Manual inspection is required.
5. **BYTEA storage for photos.** Acceptable at current scale. Revisit at multi-practice volume.
6. **Nightly deletion timing.** Minimum retention is ~5.25 hours; maximum ~24 hours. Both are within acceptable data protection bounds.
7. **`pdf_jobs` and `delivery_jobs` accumulate indefinitely.** They serve as an operational audit trail. Storage cost is trivial. Periodic cleanup can be added later.
8. **CRITICAL-level logging is the sole alerting mechanism.** Structured error reporting should be revisited in a future ticket.
9. **Alternative delivery backup and admin portal notification for delivery failures** are planned as a separate ticket, before collecting real patient data.
10. **Migration D edge case.** If Migration D runs while a PDF job is mid-flight, the worker's retry will succeed because `delivery_email` and `attachment_count` are read from `pdf_jobs`, not `submission_records`. No data loss occurs.
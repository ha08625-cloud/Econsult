# Submission, Serialization & Delivery

**LLM INSTRUCTIONS:** This document covers design decisions and strict boundaries for the submission domain. Read the actual source files for function signatures, field names, and schema details.

---

## Scope

Finalizing forms, persisting submission records, auditing, photo storage, PDF generation, attachment storage, and delivering clinical output to the practice via a three-stage async pipeline.

**Key files:** `serialisation.py`, `serialisation_contracts.py`, `submission_repository.py`, `attachment_repository.py`, `photo_repository.py`, `delivery_service.py`, `delivery_constants.py`, `pdf_formatter.py`, `pdf_repository.py`, `pdf_constants.py`, `delivery_repository.py`, `downstream_enqueuer.py`, `pdf_worker.py`, `pdf_worker_main.py`, `delivery_worker.py`, `worker_main.py`, `deletion_job.py`, `webhook_router.py`

---

## Pipeline Architecture

The system uses a three-stage async pipeline. The web request persists the submission and raw photos, the PDF worker generates the PDF and enqueues delivery, and the delivery worker sends the email. Each stage owns its own table and communicates only via job creation.

```
HTTP request (form_router.py)
  -> submission_records (create)
  -> submission_photos (save raw photos)
  -> pdf_jobs (enqueue)

PDF worker (pdf_worker.py)
  -> submission_photos (read)
  -> submission_attachments (UPSERT pdf bytes)
  -> delivery_jobs (enqueue)
  -> pdf_jobs (mark done)

Delivery worker (delivery_worker.py)
  -> delivery_jobs (claim)
  -> submission_attachments (read pdf bytes)
  -> email send (Mailgun HTTP or SMTP)
  -> delivery_jobs (mark_as_accepted with provider_message_id — Mailgun path)
  -> delivery_jobs (mark_sent — SMTP/legacy path)

Mailgun webhook (webhook_router.py)
  -> delivery_jobs (mark_delivered or mark_provider_failed, append_provider_event)

Deletion cron (deletion_job.py)
  -> submission_photos (delete where delivered)
  -> submission_attachments (delete where delivered)
```

---

## Submission Lifecycle Invariants

- A `submission_records` row MUST be created before any child rows (`submission_photos`, `pdf_jobs`). It is the FK target for all downstream tables.
- The PDF stored in `submission_attachments` is the canonical delivery artifact. It is generated once by the PDF worker and sent as-is on every delivery attempt, including retries. The submission is immutable from the moment the patient clicks submit.
- `condition_label` is stored denormalised on `submission_records` at submission time. Historical records retain the label that was active when the patient submitted, even if the ruleset is later updated.
- Delivery failures are operational, not clinical. They are never surfaced to the patient. The patient always receives a submission ID regardless of delivery outcome.
- `delivery_email` is captured at submission time and stored on `pdf_jobs.delivery_email`. It does not appear on `submission_records`. Historical audits reflect the actual address used even if the practice email is later changed.

---

## Ordering Invariant (PDF Worker)

**This invariant must never be broken by future changes.**

Within the PDF worker, operations on a single job execute in this order:

1. `save_attachment` (UPSERT — safe on retry)
2. `downstream.enqueue` (idempotent — underlying repos use ON CONFLICT DO NOTHING)
3. `pdf_repo.mark_done`

A downstream queue row can only exist after `save_attachment` has completed successfully. This guarantees the next worker (the delivery worker on the email path, or the PDS worker on the future MESH path) will always find an attachment when it claims its job. There is no need to handle a missing attachment as a normal case in any downstream worker — if the attachment is absent, the invariant has been broken and the error should propagate loudly.

The active `downstream` adapter is selected at worker startup by `pdf_worker_main.py` based on `MESH_DELIVERY`. In the email-only configuration, the adapter is `DeliveryEnqueuer`, which dispatches to `delivery_repo.create_job`. The PDF worker itself is downstream-agnostic.

**Crash recovery at each step:**

| Crash point | State | Recovery |
|---|---|---|
| Before `save_attachment` | No attachment, no downstream queue row | PDF worker retries; regenerates PDF from stored photos |
| After `save_attachment`, before `downstream.enqueue` | Attachment exists, no downstream queue row | UPSERT is safe; worker enqueues downstream then marks done |
| After `downstream.enqueue`, before `mark_done` | Attachment and downstream queue row both exist | Both UPSERT and the downstream's idempotent insert fire safely; worker marks done |
| After `mark_done` | Job is done; not re-claimed | No action needed |

There is no crash point that leaves the system in an irrecoverable state without operator intervention.

---

## Job Tables

### `pdf_jobs`

One row per submission. Created by `form_router.py` immediately after saving photos. Polled by the PDF worker.

Status values: `pending`, `done`, `failed`.

`attachment_count` and `delivery_email` are captured at job creation time by the form router. The PDF worker reads them from the job row, not from `submission_records`. This is why these columns were dropped from `submission_records` in Migration 0013 — they live exclusively on `pdf_jobs`.

`status` remains `pending` throughout all retries until `mark_done` succeeds or `MAX_PDF_ATTEMPTS` is exhausted (at which point it becomes `failed` permanently).

### `delivery_jobs`

One row per submission. Created by the PDF worker as the second-to-last step of processing. Polled by the delivery worker.

Status values: `pending`, `provider_accepted`, `delivered`, `sent`, `failed`.

| Status | Set by | Meaning |
|---|---|---|
| `pending` | PDF worker (`create_job`) | Awaiting delivery attempt |
| `provider_accepted` | Delivery worker (`mark_as_accepted`) | Mailgun API accepted the message; webhook pending |
| `delivered` | Webhook router (`mark_delivered`) | Mailgun confirmed delivery to recipient mail server |
| `sent` | Delivery worker (`mark_sent`) | SMTP/legacy path; no webhook tracking available |
| `failed` | Delivery worker (`mark_failed`) or webhook router (`mark_provider_failed`) | Permanent failure |

`to_email`, `condition_label`, and `submitted_at` are denormalised at creation time so the delivery worker never needs to read `submission_records`.

The `submission_id` column has a UNIQUE constraint. `create_job` uses ON CONFLICT DO NOTHING, making it safe to call multiple times for the same submission without inserting a duplicate.

`provider_message_id` (VARCHAR 255, indexed) is populated by the delivery worker immediately after a successful Mailgun API call. The webhook router uses this as the lookup key when matching incoming delivery signals to jobs.

`provider_events` (JSONB, append-only) stores the raw payloads of all received Mailgun webhook events for a lossless audit trail.

---

## Job Claiming (SKIP LOCKED)

Both `PDFRepository.claim_next_pending` and `DeliveryRepository.claim_next_pending` use `SELECT ... FOR UPDATE SKIP LOCKED`. The lock is held only for the duration of the claim transaction, which immediately sets `next_retry_after` to 10 minutes in the future. This moves the job outside the eligible window before the lock is released, preventing a second worker from claiming the same job without requiring a `status = processing` column or a long-held lock.

`claim_next_pending` filters exclusively on `status = 'pending'`. Jobs in `provider_accepted`, `delivered`, `sent`, or `failed` status are never re-claimed. A `provider_accepted` job must not be re-processed by the delivery worker — its status transitions exclusively via the webhook router.

---

## Retry Schedule

### PDF jobs (`pdf_constants.py`)

`MAX_PDF_ATTEMPTS = 3`. Backoff: `[5, 10]` minutes. After 3 failures the job is marked `failed` permanently.

### Delivery jobs (`delivery_constants.py`)

`MAX_ATTEMPTS = 4` (derived from `len(RETRY_BACKOFF_MINUTES) + 1`). Backoff: `[1, 10, 60]` minutes. Total retry window: 71 minutes. This is deliberately short for clinical safety.

---

## Webhook Infrastructure

### Security model (`webhook_router.py`)

The webhook endpoint (`POST /webhooks/mailgun`) enforces three security checks in order before processing any event:

1. **Timestamp check.** Webhooks with a timestamp older than 15 minutes are silently dropped (200 OK). This prevents stale replays and bounds the useful lifetime of tokens in the replay table.

2. **HMAC verification.** The `signature` field in the payload is verified against `MAILGUN_SIGNING_KEY` using HMAC-SHA256 over `(timestamp + token)`. Requests failing verification return 403. `hmac.compare_digest` is used to prevent timing attacks. `MAILGUN_SIGNING_KEY` is required at startup when `MAILGUN_API_KEY` is set.

3. **Replay protection.** Each webhook carries a unique `token`. The router deletes expired tokens (older than 15 minutes) then attempts `INSERT INTO webhook_tokens (token) ... ON CONFLICT DO NOTHING`. If no row is inserted the token was already seen — the request is a replay and returns 200 OK silently. This keeps the `webhook_tokens` table bounded without a separate cron job.

### Race condition handling

If a webhook arrives before the delivery worker has committed `provider_message_id` to `delivery_jobs`, the router returns 406 Not Acceptable. Mailgun retries with exponential backoff. This leverages the provider's built-in retry logic rather than holding open a synchronous connection.

### Event processing

| Mailgun event | Status transition | Payload appended |
|---|---|---|
| `delivered` | `provider_accepted` -> `delivered` | Yes |
| `failed` | `provider_accepted` -> `failed` | Yes |
| `dropped` | `provider_accepted` -> `failed` | Yes |
| any other | none | Yes |

All events append the raw payload to `provider_events` regardless of whether a status change occurs.

---

## Data Retention & Deletion

Photos (`submission_photos`) and PDF attachments (`submission_attachments`) are deleted nightly by `deletion_job.py` for all submissions where `delivery_jobs.status = 'delivered'`.

- Minimum retention: ~5.25 hours (submission at 6:45pm grace window close, delivered webhook received, deletion at midnight).
- Maximum retention: ~24 hours (submission at practice open, delivered webhook received next day, deletion next midnight).

Jobs on the SMTP/legacy path (`status = 'sent'`) are not deleted by the current deletion job. This is a known limitation — see Known Limitations below.

`pdf_jobs` and `delivery_jobs` rows are never deleted. They accumulate as an operational audit trail. Storage cost is trivial (no blobs). A periodic cleanup can be added later if needed.

The long-term clinical record is `clinical_output_json` and `audit_output_json` on `submission_records`, which contain no photos.

---

## Defensive Photo Count Check (PDF Worker)

After claiming a PDF job, the PDF worker compares `len(photos)` from `photo_repository.get_photos` against `job.attachment_count` (stored on the `pdf_jobs` row at creation time). If they do not match, the job is failed immediately without generating a PDF or creating a delivery job. This is a safety net against partial photo persistence caused by a router crash mid-save, and is separate from orphan detection.

---

## Image Sanitization (CDR)

The form router applies Content Disarm and Reconstruction (CDR) to every uploaded photo before any database write. The implementation is in `app/utils/image_sanitizer.py`.

**What CDR does:**

Each image is fully decoded by Pillow via `convert("RGB")` — which must be called before `thumbnail()`, since `thumbnail()` on a palette-mode or RGBA image can behave unexpectedly — and then re-encoded from scratch as a JPEG. The output buffer is written fresh; no data from the original file is carried through except the decoded pixel values.

**Tier-aware resize and quality:**

The sanitizer accepts a `tier` parameter passed from `form_router.py`:

- `"high"` — targets 4K (3840px long edge) at quality 85. Intended for clinical close-ups where a clinician may zoom to 200% or beyond.
- `"standard"` — targets 1080p (1920px long edge) at quality 80. Intended for documents and general photos.

Resize uses `Image.thumbnail()`, which never upscales — if the image is already within the target bounds it is left at its original dimensions.

**EMIS 5 MB output enforcement (high tier):**

After the initial encode, if the output exceeds 5 MB, the high-tier path iterates through two fallback attempts before giving up:

1. Quality 80 at 3840px — allows clinician zoom to approximately 200% with minimal quality loss.
2. Quality 85 at 2560px — allows clinician zoom to approximately 150% with minimal quality loss.

If all three attempts produce output over 5 MB, `sanitize_image` raises `ImageTooLargeError` (a subclass of `ValueError`) with a patient-facing message. `form_router.py` catches this and returns 422. Standard-tier submissions use a single encode step — 1080p at quality 80 reliably stays within 5 MB for any realistic source image and does not require iteration.

**Security properties:**

- **Full-decode validation.** The previous `verify()` call checked the file header only. A file with a valid header but a truncated or corrupt body would pass `verify()` but then fail during PDF generation, leaving the submission unrecoverable. CDR catches this at the router: the full decode fails, the router returns 422, and no database write occurs.
- **Metadata stripping.** EXIF data, ICC profiles, and all other metadata are discarded. Pillow does not carry these through `convert("RGB")` when no explicit `exif=` argument is passed to `save()`.
- **Format normalisation.** Output is always JPEG regardless of whether the input was JPEG or PNG. Bytes stored in `submission_photos` are always sanitized JPEG.
- **Structural polyglot defence.** A polyglot file embeds a second payload in regions Pillow ignores — for example, bytes appended after the JPEG EOI marker. Because CDR re-encodes from the decoded pixel buffer rather than forwarding the original bytes, any such appended payload is discarded and never reaches the database or the PDF worker.

**Post-sanitization size check:**

After CDR, the router re-validates each image against `MAX_FILE_SIZE_BYTES` and the combined total against `MAX_TOTAL_SIZE_BYTES`. This is necessary because re-encoding an already-compressed JPEG can marginally increase its size. In practice this is rare, but the invariant that stored bytes are within the declared limits must be maintained.

**Failure behaviour:**

If CDR raises for any photo, the router returns 422. No database writes have occurred at this point. The entire submission is rejected.

**Known limitation — lossy PNG conversion:**

PNG-to-JPEG conversion is lossy. This is accepted because PNG uploads in this system are almost always screenshots rather than clinical photographs requiring maximum fidelity. This decision should be revisited if the system is extended to use cases where PNG fidelity matters clinically.

---

## Design Decisions

### Output Contracts (`serialisation_contracts.py`)

Two output types with distinct purposes:

- **`ClinicalOutput`** — lossy by design. Strips provenance and encoder internals. Safe for clinical and patient use. Contains `question_labels` (answer_key -> question text at submission time) so the record is self-contained and interpretable without reloading the ruleset. Provides a `from_dict` classmethod for reconstructing from the JSONB dict returned by psycopg2, which handles the nested `PatientDetails` dataclass.
- **`AuditOutput`** — lossless. Contains full `runtime_state` snapshot, safety evaluation, ruleset version, and `photo_quality_tier`. Intended for debugging, safety review, and regulatory inspection. `photo_quality_tier` is stamped by `form_router.py` after `finish_runtime_state()` returns using `dataclasses.replace()` — the clinical pipeline has no knowledge of the HTTP submission tier. It is `None` for text-only submissions and for historical records predating the field.

Neither contract may be used as an input back into the engine. This module contains no logic beyond the `from_dict` reconstruction helper.

### Serialisation (`serialisation.py`)

- Produces `ClientStateView` (for frontend rendering), `ClinicalOutput`, and `AuditOutput`.
- Serialisation never mutates state.
- `condition_label` is passed in explicitly by the calling layer. This module never accesses presentation metadata from the ruleset directly.

### Submission Repository (`submission_repository.py`)

Owns the `submission_records` table. Responsible only for `create_submission` and `get_submission`. Delivery status tracking, retry queries, and orphan detection have moved to `DeliveryRepository` and `PDFRepository`.

`_SUBMISSION_COLUMNS` is an explicit column list used in all SELECT queries. Never use `SELECT *`. This constant must be updated when migrations add or remove columns. The delivery columns (`delivery_status`, `delivery_email`, etc.) were removed by Migration 0013 and are no longer present.

`create_submission` no longer accepts `delivery_email` or `attachment_count` — these are now captured on `pdf_jobs` at job creation time. It uses named `%(name)s` parameters rather than positional `%s` placeholders to make the column-to-value mapping explicit.

### Attachment Repository (`attachment_repository.py`)

Owns the `submission_attachments` table. `save_attachment` is an UPSERT (`ON CONFLICT (submission_id) DO UPDATE SET pdf_bytes = EXCLUDED.pdf_bytes`) to support safe PDF worker retries. PDF generation from the same inputs is deterministic, so overwriting is safe.

`get_attachment` raises `AttachmentNotFound` if absent. A missing attachment at delivery time is always an error — the ordering invariant guarantees it cannot happen under normal operation.

Attachments are stored as BYTEA in Postgres. At current scale (~5 photos/day, nightly cleanup) this is acceptable. If the system scales to multiple practices with high photo volume, BYTEA storage will cause WAL bloat, expensive vacuuming, and slow backups. Migrate to object storage (S3/equivalent) at that point.

### Photo Repository (`photo_repository.py`)

Owns the `submission_photos` table. `save_photos` inserts one row per photo with `photo_index` from enumeration (0-based) to preserve upload order. `get_photos` returns bytes ordered by `photo_index`. No delete method is provided — photo deletion is exclusively the responsibility of `deletion_job.py`.

### Delivery Service (`delivery_service.py`)

Abstract base class (`DeliveryService`) with three concrete implementations:

- **`MailgunHttpDeliveryService`** — default for production. Sends via the Mailgun EU HTTP API (`https://api.eu.mailgun.net/v3/{domain}/messages`). Requires `MAILGUN_API_KEY`, `MAILGUN_DOMAIN`, and `EMAIL_FROM`. Returns the Mailgun message ID string (angle brackets stripped) so the delivery worker can persist it as `provider_message_id`.
- **`EmailDeliveryService`** — alternative (unlikely to be needed). SMTP configuration read from environment variables at instantiation time. Returns `None` — no webhook tracking available on the SMTP path.
- **`ConsoleDeliveryService`** — development only. Raises `RuntimeError` at instantiation if `DEV_MODE` is not set. Returns `None`.

Service selection in `main.py` and `worker_main.py`: `DEV_MODE=1` -> Console; `MAILGUN_API_KEY` set -> Mailgun HTTP; otherwise -> SMTP.

`send_clinical_output` returns `str | None`. The delivery worker branches on this: a string triggers `mark_as_accepted` (Mailgun path); `None` triggers `mark_sent` (SMTP/legacy path).

Must never: access the database, update delivery status, import engine modules, generate PDFs, or retry on failure.

---

## What Was Removed in Commit 2

- `delivery_orchestration.py` — synchronous delivery logic, no longer used.
- `delivery_events.py` — string constants used only by `delivery_orchestration.py`.
- `PendingDelivery` dataclass from `submission_repository.py`.
- `delivery_status`, `delivery_email`, `delivered_at`, `delivery_error`, `delivery_attempts`, `last_attempt_at`, `next_retry_after`, `attachment_count` columns from `submission_records` (Migration 0013).
- `list_retryable`, `list_orphans`, `record_attempt_outcome`, `get_pending_delivery`, `update_delivery_status` methods from `SubmissionRepository`.
- `test_delivery_orchestration.py`.

---

## Known Limitations

1. **Duplicate delivery on crash.** A process crash after a successful send but before `mark_as_accepted` (Mailgun) or `mark_sent` (SMTP) commits results in a re-send on the next retry. Duplicate delivery is safer than silently dropping a submission.
2. **No health check or liveness probe for workers.** Railway process restart is the only recovery mechanism for a stuck worker. Explicitly deferred. Revisit before scaling to multiple practices.
3. **Orphan submissions require operator intervention.** If the router crashes between `create_submission` and `pdf_repo.create_job`, the orphan detection query finds the submission but automation cannot determine whether photos were fully saved. Manual inspection is required.
4. **BYTEA storage for photos.** Acceptable at current scale. Revisit at multi-practice volume.
5. **Nightly deletion timing.** Minimum retention is ~5.25 hours; maximum ~24 hours. Both are within acceptable data protection bounds for the Mailgun webhook path.
6. **`pdf_jobs` and `delivery_jobs` accumulate indefinitely.** They serve as an operational audit trail. Storage cost is trivial. Periodic cleanup can be added later.
7. **Exhaustion is logged but not actively alerted.** `DeliveryRepository.mark_failed` returns `True` when a job is permanently exhausted (status transitions to `failed`). `run_worker` captures this and emits a dedicated `ERROR`-level log including `submission_id`, `job_id`, and `MAX_ATTEMPTS`. Structured alerting (e.g. Sentry) is planned as a separate ticket, before collecting real patient data.
8. **Alternative delivery backup and admin portal notification for delivery failures** are planned as a separate ticket, before collecting real patient data.
9. **SMTP path data retention is unbounded.** Submissions delivered via SMTP reach `status = 'sent'`, not `'delivered'`. The deletion job filters on `'delivered'` only, so photos and attachments for SMTP-delivered submissions are never deleted by the current job. This will be resolved when the backup delivery and notification architecture is implemented.
10. **`provider_accepted` with no webhook.** If Mailgun accepts a message but the `delivered` webhook never arrives (provider outage, permanent failure without a `failed` event), the job remains in `provider_accepted` indefinitely and its photos and attachments are never deleted. This is an accepted known limitation until the backup delivery and notification architecture is implemented.
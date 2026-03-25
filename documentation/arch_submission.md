# Submission, Serialization & Delivery

**LLM INSTRUCTIONS:** This document covers design decisions and strict boundaries for the submission domain. Read the actual source files for function signatures, field names, and schema details.

---

## Scope

Finalizing forms, persisting submission records, auditing, and sending clinical output to the practice.

**Key files:** `serialisation.py`, `serialisation_contracts.py`, `submission_repository.py`, `attachment_repository.py`, `delivery_service.py`, `app/utils/pdf_formatter.py`

---

## Submission Lifecycle — Critical Invariants

- A `submission_record` MUST be created in the database with `delivery_status = "pending"` **before** any delivery is attempted. This ensures the record exists even if the process crashes during delivery.
- The PDF stored in `submission_attachments` is the **canonical delivery artifact**. It is generated once at submission time and must never be regenerated. Whatever was in the PDF at submission time is what gets sent on every delivery attempt, including retries. This is correct clinical behaviour — the submission is immutable from the moment the patient clicks submit.
- `condition_label` is stored denormalised on `submission_records` for lightweight access during delivery without loading `clinical_output_json`. If a condition label is later changed in the ruleset, historical records retain the label that was active when the patient submitted. This is intentional — it preserves the clinical context at submission time.
- Delivery failures are **operational, not clinical**. They are never surfaced to the patient. The patient always receives a submission ID regardless of delivery outcome.
- No automatic retry is implemented. Retry decisions belong to the calling layer, not the repository or delivery service.
- `delivery_email` is captured from the practice record **at submission time** and stored in the submission record. Historical audits reflect the actual address used even if the practice email is later changed.

---

## Design Decisions

### Output Contracts (`serialisation_contracts.py`)

There are two output types, each with a distinct purpose:

- **`ClinicalOutput`** — lossy by design. Strips provenance and encoder internals. Safe for clinical and patient use. Contains `question_labels` (answer_key → question text at submission time) so the record is self-contained and interpretable without reloading the ruleset. Also carries `contact_preferences` — these are stored here so the clinical record is self-contained and the delivery service receives everything it needs in a single argument.
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

`send_clinical_output` accepts `to_email`, `condition_label`, `clinical_output`, `submission_id`, `submitted_at`, and `pdf_bytes`. PDF generation is a submission-time concern, not a delivery concern — the caller generates the PDF once and passes pre-rendered bytes. The delivery service attaches these bytes to the email without modification. `ClinicalOutput` is still used to build the plain-text email body.

`contact_preferences` are read from inside `ClinicalOutput` — the delivery interface does not receive a separate preferences argument.

`EmailDeliveryError` is raised on any SMTP failure. The calling layer (the router) catches it, logs it, and records `delivery_status = "failed"` against the submission — it must never propagate as an HTTP error.

The delivery service must never: access the database, update delivery status, import engine modules, generate PDFs, or retry on failure.

### PDF Formatter (`app/utils/pdf_formatter.py`)

- Pure function `generate_pdf()` — takes `ClinicalOutput`, metadata, and optional `practice_name`; returns raw PDF bytes.
- No database access, no imports from routers or delivery service.
- Sections mirror the plain-text email body exactly, so both outputs carry the same information in the same order.
- Called by `form_router.py` at submission time. The returned bytes are stored in `submission_attachments` and passed to the delivery service. The PDF is never regenerated.
- `practice_name` is injected into the router via `get_practice_name` dependency and passed directly to `generate_pdf`. The name is captured once at startup. If the practice name is changed via the admin interface, PDFs will show the old name until the next server restart — this is a known and accepted limitation.

---

## Startup Validation (enforced in `main.py`)

These conditions abort startup rather than silently degrade:

- `PRACTICE_ID` env var not set
- Database contains more than one practice
- `PRACTICE_ID` does not match any practice in the database
- Practice has no email address
- SMTP env vars not set in production mode

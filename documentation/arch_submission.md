# Submission, Serialization & Delivery

**LLM INSTRUCTIONS:** This document covers design decisions and strict boundaries for the submission domain. Read the actual source files for function signatures, field names, and schema details.

---

## Scope

Finalizing forms, persisting submission records, auditing, and sending clinical output by email.

**Key files:** `serialisation.py`, `serialisation_contracts.py`, `submission_repository.py`, `email_service.py`

---

## Submission Lifecycle — Critical Invariants

- A `submission_record` MUST be created in the database with `delivery_status = "pending"` **before** any email send is attempted. This ensures the record exists even if the process crashes during delivery.
- Email delivery failures are **operational, not clinical**. They are never surfaced to the patient. The patient always receives a submission ID regardless of delivery outcome.
- No automatic retry is implemented. Retry decisions belong to the calling layer, not the repository or email service.
- `delivery_email` is captured from the practice record **at submission time** and stored in the submission record. Historical audits reflect the actual address used even if the practice email is later changed.

---

## Design Decisions

### Output Contracts (`serialisation_contracts.py`)

There are two output types, each with a distinct purpose:

- **`ClinicalOutput`** — lossy by design. Strips provenance and encoder internals. Safe for clinical and patient use. Contains `question_labels` (answer_key → question text at submission time) so the record is self-contained and interpretable without reloading the ruleset.
- **`AuditOutput`** — lossless. Contains full `runtime_state` snapshot, safety evaluation, and ruleset version. Intended for debugging, safety review, and regulatory inspection.

Neither contract may be used as an input back into the engine. This module contains no logic.

**Note on `additional_text`:** `ClinicalOutput` includes an `additional_text` field (separate from `free_text`). Check `serialisation_contracts.py` for the current field list — the doc should not be the source of truth for field names.

### Serialisation (`serialisation.py`)

- Produces `ClientStateView` (for frontend rendering), `ClinicalOutput`, and `AuditOutput`.
- Serialisation **never mutates state**.
- `condition_label` is passed in explicitly by the calling layer. This module never accesses presentation metadata from the ruleset directly.
- The ruleset parameter is used only for question text and `answer_type`, never for presentation data.

### Submission Repository (`submission_repository.py`)

- Owns the `submission_records` table.
- `delivery_status` values: `"pending"`, `"sent"`, `"failed"`.
- `list_by_status` raises `InvalidDeliveryStatus` on unrecognised values. A typo must not silently return an empty list when the caller expected failures.
- Must never: send emails, import engine modules, or make retry decisions.

### Email Service (`email_service.py`)

- Formats `ClinicalOutput` as a plain text email and sends via SMTP.
- In `DEV_MODE`, skips sending and logs the full email to stdout instead.
- `contact_preferences` is an optional dict passed through from the finish payload. When present, a contact preferences section is appended to the email body. Fields within it are omitted if null or empty — they are never printed as `"None"`. Validation of this dict happens upstream in `request_validation.py`, not here.
- `contact_preferences` is a plain dict, not a typed dataclass. It is presentation-only data with no clinical significance. Read `email_service.py` directly for the current expected fields.
- Raises `EmailDeliveryError` on any SMTP failure. The error message is suitable for storage in `submission_records.delivery_error`.
- Must never: access the database, update delivery status, import engine modules, or retry on failure.

---

## Startup Validation (enforced in `main.py`)

These conditions abort startup rather than silently degrade:

- `PRACTICE_ID` env var not set
- Database contains more than one practice
- `PRACTICE_ID` does not match any practice in the database
- Practice has no email address
- SMTP env vars not set in production mode

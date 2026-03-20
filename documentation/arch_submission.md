# Submission, Serialization & Delivery

**LLM INSTRUCTIONS:** This document covers design decisions and strict boundaries for the submission domain. Read the actual source files for function signatures, field names, and schema details.

---

## Scope

Finalizing forms, persisting submission records, auditing, and sending clinical output to the practice.

**Key files:** `serialisation.py`, `serialisation_contracts.py`, `submission_repository.py`, `delivery_service.py`

---

## Submission Lifecycle — Critical Invariants

- A `submission_record` MUST be created in the database with `delivery_status = "pending"` **before** any delivery is attempted. This ensures the record exists even if the process crashes during delivery.
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
- Must never: send emails, import engine modules, or make retry decisions.

### Delivery Service (`delivery_service.py`)

The delivery service is an abstract base class (`DeliveryService`) with two concrete implementations selected at startup by `main.py` based on `DEV_MODE`:

- **`EmailDeliveryService`** — production implementation. Reads SMTP configuration from environment variables **at instantiation time** (`__init__`), not at send time. This means a misconfigured deployment fails immediately at startup rather than silently at the moment of the first submission.
- **`ConsoleDeliveryService`** — development only. Logs the full email payload to stdout. Raises `RuntimeError` at instantiation if `DEV_MODE` is not set, preventing accidental use in production.

`contact_preferences` are read from inside `ClinicalOutput` — the delivery interface takes only `to_email`, `condition_label`, `clinical_output`, and `submission_id`. The service never receives a separate preferences argument.

`EmailDeliveryError` is raised on any SMTP failure. The calling layer (the router) catches it, logs it, and records `delivery_status = "failed"` against the submission — it must never propagate as an HTTP error.

The delivery service must never: access the database, update delivery status, import engine modules, or retry on failure.

---

## Startup Validation (enforced in `main.py`)

These conditions abort startup rather than silently degrade:

- `PRACTICE_ID` env var not set
- Database contains more than one practice
- `PRACTICE_ID` does not match any practice in the database
- Practice has no email address
- SMTP env vars not set in production mode

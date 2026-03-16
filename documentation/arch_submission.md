**Scope:** Finalizing forms, auditing, persisting submission records, sending emails.
**Key Files:** `serialization.py`, `serialisation_contracts.py`, `submission_repository.py`, `email_service.py`


## Validation
* PRACTICE_ID environment variable not set → startup abort
* Database contains more than one practice → startup abort
* PRACTICE_ID does not match any practice in database → startup abort
* Practice has no email address → startup abort
* SMTP environment variables not set in production mode → startup abort

## Submission & Delivery Lifecycle
* Transaction Order: On form/finish, a submission_record MUST be created in the database with delivery_status = "pending" BEFORE any email send is attempted. This ensures the record exists even if the process crashes during delivery.
* Outcomes: >   * Success -> delivery_status = "sent", delivered_at = now.
* Failure -> delivery_status = "failed", delivery_error = exception message.
* Failures are Operational, not Clinical: Email failures are NOT surfaced to the patient and NO automatic retry is implemented. The patient receives a submission ID regardless of delivery outcome.
* Audit Integrity: delivery_email is captured from the practice record at submission time and hardcoded into the submission record so historical audits reflect the actual address used.

### serialization.py — Output views

Responsibilities:
* Produce ClientStateView (for frontend rendering)
* Produce ClinicalOutput (lossy, portable)
* Produce AuditOutput (lossless, for debugging and regulation)

Functions:
* serialize_client_state(runtime, ruleset, condition_label) → dict
* clinical_output(runtime) → ClinicalOutput
* audit_output(runtime) → AuditOutput

Dependencies:
* runtime_state.py (RuntimeState)
* serialisation_contracts.py (ClinicalOutput, AuditOutput)

Rules:
* Serialisation never mutates state
* Clinical output excludes encoder internals
* condition_label is passed in explicitly by the calling layer;
  this function never accesses presentation metadata from the ruleset
* RuntimeState must never be mutated or destroyed by serialisation,
  only read and projected

Architectural guarantee:
This module never accesses presentation metadata directly.
The condition_label for ClientStateView is passed in explicitly
by the calling layer. The ruleset parameter is used only for
question text and answer_type, never for presentation data.

### serialisation_contracts.py

Defines the explicit, immutable data structures that may leave the core
form engine as serialized outputs.

These contracts enforce a hard boundary between:
- Internal runtime state (lossless, mutable, provenance-aware)
- External outputs (lossy or lossless, immutable, purpose-specific)

This module contains no logic and no knowledge of RuntimeState internals.
It exists to make output schemas explicit, inspectable, and enforceable.

Key principles:
- ClinicalOutput is lossy by design and safe for clinical and patient use
- AuditOutput is lossless and intended for debugging, safety review, and regulation
- Neither contract may be used as an input back into the engine

ClinicalOutput fields:
- condition_id: str
- free_text: str
- answers: Dict[str, Any] — answer values only, no provenance
- safety_messages: List[dict]
- question_labels: Dict[str, str] — answer_key to question text at submission time

question_labels is populated by serialisation.py from the ruleset at submission
time. Storing it in ClinicalOutput means the record is self-contained: a future
reader can interpret answers without reloading the ruleset. If the question text
ever changes, historical submissions still reflect the wording that was shown to
the patient.

### submission_repository.py — Submission record database access

Responsibilities:
- Initialise submission_records table on startup
- Create submission records at form completion
- Update delivery status after email send attempt
- Retrieve and list submission records for manual inspection

Public interface:
- create_submission(submission_id, practice_id, condition_id,
  clinical_output, audit_output, delivery_email) → None
- update_delivery_status(submission_id, status,
  delivered_at=None, delivery_error=None) → None
- get_submission(submission_id) → dict
- list_by_status(status) → list[dict]

delivery_status values: "pending", "sent", "failed"
list_by_status raises InvalidDeliveryStatus on unrecognised values — a typo
must not silently return an empty list when the caller expected failures.

delivery_email is stored at submission time from the practice record, not
looked up later. This means the audit trail reflects where the form was
actually sent, even if the practice email is updated afterwards.

This module must never:
- Send emails (that belongs in email_service)
- Import engine modules
- Make retry decisions (that belongs in the calling layer)

### email_service.py — Clinical output email delivery

Responsibilities:
- Format clinical output as a plain text email body
- Send via SMTP in production mode
- Log to stdout in DEV_MODE without sending

Configuration via environment variables:
- SMTP_HOST, SMTP_PORT (default 587), SMTP_USER, SMTP_PASSWORD, EMAIL_FROM
- SMTP_TIMEOUT (default 30 seconds)
- DEV_MODE=1: skips sending, logs full email content to stdout

Public interface:
- send_clinical_output(to_email, condition_label, clinical_output,
  submission_id, contact_preferences=None) → None

contact_preferences is an optional dict passed through from the finish
payload. When present, a CONTACT PREFERENCES section is appended to the
email body after the clinical content. When absent or None, the section
is omitted entirely. Null optional fields within the block (phone_number,
best_time_to_call, usual_doctor_name) are omitted line-by-line rather
than printed as "None".

contact_preferences is accepted as a plain dict, not a typed dataclass.
It is presentation-only data with no clinical significance and no need
for engine-level typing. The email service is not responsible for
validating it — that is done upstream in request_validation.py.

Raises EmailDeliveryError on any SMTP failure. The error message is
suitable for storage in submission_records.delivery_error.

Email body uses clinical_output.question_labels for human-readable answer
labels. Falls back to the raw answer_key if a label is missing.

This module must never:
- Access the database
- Update delivery status (that belongs in submission_repository)
- Import engine modules or condition_registry
- Retry on failure

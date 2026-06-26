# MESH Dispatcher & NHS Delivery

**LLM INSTRUCTIONS:** This document covers design decisions and strict boundaries for the MESH dispatch path — the NHS transport alternative to the Mailgun email path. Read the actual source files for function signatures, field names, and schema details. The phased rollout plan, NHS protocol facts, and production enablement gates live in `mesh_integration_plan.md` and `nhs_integration_reference.md`; this document covers only the design decisions for code that has already shipped.

---

## Scope

Dispatching clinical PDFs to a GP practice over the NHS MESH network, falling back to the existing Mailgun email path on terminal MESH failure, and the `mesh_jobs` table lifecycle. mTLS transport security (client certs, CA verification, sandbox parity) is documented separately in `docs/arch_security.md`, section 8, "MESH Outbound TLS."

**Key files:** `client.py` (`MeshClient`), `mesh_enqueuer.py`, `mesh_payload.py`, `mesh_repository.py`, `mesh_constants.py`, `mesh_worker.py`, `mesh_worker_main.py`, `app/services/delivery/mesh/errors.py`, `0005_mesh_schema.py`

---

## Relationship to the Email Pipeline

MESH and Mailgun email are both "downstream" consumers selected by the `DownstreamEnqueuer` seam at PDF worker startup, based on the `MESH_DELIVERY` env var. The PDF worker itself is downstream-agnostic — this invariant, and the crash-recovery table for `save_attachment` / `downstream.enqueue` / `mark_done`, are documented in `docs/arch_submission.md`, "Ordering Invariant (PDF Worker)." Everything from `mesh_jobs` creation onward is exclusive to the MESH path and documented here.

---

## MESH Dispatcher (Phase 3)

`app/services/delivery/mesh_worker.py`, entry point `mesh_worker_main.py`. Claims `mesh_jobs` rows, builds the payload via the `MeshPayloadBuilder` seam (`mesh_payload.py` — only `RawPdfPayloadBuilder` ships; it is provisional, see `mesh_integration_plan.md` "Payload status: provisional"), and POSTs to MESH. The workflow ID is env-driven (`MESH_WORKFLOW_ID`).

### Fallback Ordering Invariant

**This invariant must never be broken by future changes.**

On terminal MESH failure, or transient exhaustion (`MAX_MESH_ATTEMPTS`), the dispatcher executes in this order:

1. `mesh_repo.mark_fallback_triggered`
2. `delivery_repo.create_job(..., is_fallback=True)` (idempotent — ON CONFLICT DO NOTHING)

The order fails safe: a crash between the two leaves the submission undelivered but detectable (a `fallback_triggered` row with no `delivery_jobs` row), never double-sent on both channels. The **orphaned-fallback recovery sweep** at the top of every dispatcher loop iteration repairs exactly that state by re-running the idempotent `create_job`, logging at ERROR per recovery. The reverse order would risk double-channel delivery and is forbidden.

Fallback emails are IDENTICAL to email-path emails (same subject, body, attachment). `is_fallback` is operational metadata only; nothing in the delivery worker or webhook router reads it.

### Metadata Access Deviation

The delivery worker never reads `submission_records` (its metadata is denormalised onto `delivery_jobs` at enqueue time). The MESH dispatcher deviates deliberately: at fallback time it reads `to_email` from `pdf_jobs` (`PDFRepository.get_delivery_email`) and `condition_label`/`submitted_at` via the narrow `SubmissionRepository.get_delivery_metadata` — never `get_submission`, which returns clinical JSON the dispatcher has no business holding. The deviation is acceptable because `submission_records` rows are the permanent clinical record (never deleted) and the read happens only on the rare fallback path.

---

## `mesh_jobs` Table

One row per MESH-enabled submission. Created by the PDF worker via `MeshEnqueuer`; consumed by the MESH dispatcher (send) and, from Phase 4, the tracking poller (confirmation). Status lifecycle and column semantics are documented in `mesh_repository.py` and migration `0005_mesh_schema.py`. The recipient mailbox is stamped onto each row at enqueue time so a config change between enqueue and dispatch cannot misroute a queued referral.

For the SKIP LOCKED job-claiming pattern shared with `pdf_jobs` and `delivery_jobs`, see `docs/arch_submission.md`, "Job Claiming (SKIP LOCKED)."

---

## Retry Schedule

`MAX_MESH_ATTEMPTS = 4` (derived from `len(MESH_RETRY_BACKOFF_MINUTES) + 1`). Backoff: `[1, 5, 15]` minutes — deliberately shorter than the email path's ~71-minute window because a working fallback exists; on exhaustion the dispatcher falls back to email rather than parking the job. The startup handshake retries transient failures per `HANDSHAKE_RETRY_DELAYS_SECONDS` then aborts (bounded because empty-errorCode 403s classify as transient, so bad credentials must not retry forever).

---

## Data Retention — Interim Limitation (Phase 3)

Pure-MESH submissions have no `delivery_jobs` row, so they are never deletion-eligible until the Phase 4 deletion-job rewrite makes the deletion view MESH-status-aware. This is one of the reasons `MESH_DELIVERY=1` must not be enabled in production before Phase 4 — see "Production enablement gates" in `mesh_integration_plan.md`. MESH-to-Mailgun fallback submissions DO get a `delivery_jobs` row and follow the normal webhook-confirmed deletion path documented in `docs/arch_submission.md`, "Data Retention & Deletion."

---

## Outbound Security

mTLS strategy, strict-path certificate inputs, fail-fast startup validation, sandbox parity via the nginx mTLS proxy, and production cert handling are documented in `docs/arch_security.md`, section 8, "MESH Outbound TLS." This document does not duplicate that content.
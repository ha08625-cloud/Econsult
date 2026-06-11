# Phase 3 Implementation Plan (MESH Dispatcher + Mailgun Fallback)

Working document for implementing Phase 3 of `mesh_integration_plan.md` (June 2026
revision). Steps 1-4 complete.  This chat is to work on steps 5-8

## Decisions already made (do not reopen)

- Fallback email is IDENTICAL to the email path. No changes to `delivery_worker.py`
  or `delivery_service.py`. `is_fallback` is operational metadata only.
- Backoff: `MESH_RETRY_BACKOFF_MINUTES = [1, 5, 15]`, `MAX_MESH_ATTEMPTS = 4`.
- Startup handshake: bounded in-process retry on `MeshTransientError`
  (`HANDSHAKE_RETRY_DELAYS_SECONDS = [10, 30, 60, 120, 300]`), abort immediately on
  `MeshTerminalError`, abort after exhaustion. Bound exists because a 403 with empty
  errorCode classifies as transient, so bad credentials must not retry forever.
- Payload built via `MeshPayloadBuilder` seam; only `RawPdfPayloadBuilder` ships
  (provisional — see "Payload status: provisional" in the plan doc).
- Workflow ID is env-driven (`MESH_WORKFLOW_ID`), not a builder concern in this phase.
- Orphaned-fallback recovery sweep ships IN PHASE 3, runs at the top of every loop
  iteration, recovers via idempotent `delivery_repo.create_job(is_fallback=True)`,
  logs at ERROR per recovery. Sentry events for it are Phase 5.
- Dispatcher reads fallback metadata narrowly: `PDFRepository.get_delivery_email`
  (exists) + new `SubmissionRepository.get_delivery_metadata` (condition_label,
  submitted_at only — never `get_submission`, which returns clinical JSON).
- `mex_localid` column is Postgres UUID; `MeshClient.send_message` takes str —
  stringify at call site.
- Production enablement gates apply (plan doc): no `MESH_DELIVERY=1` in production
  until Phase 4 + written workflow arrangement + endpoint lookup + verified first send.

## Conventions to follow

- Worker loop shape mirrors `pdf_worker.py`: `run_worker(...)` + `_process_job(...)`,
  injected dependencies, `psycopg2.OperationalError` propagates uncaught (Railway
  restarts), per-job try/except marks failure and continues.
- Entry point mirrors `pdf_worker_main.py`: logging config, `init_telemetry`,
  `_require_env`, deferred application imports after env validation, fail-fast.
- Constants modules import no application modules (`file_structure.md` rule).
- Tests: unit tests carry no marker (run in CI); DB integration tests carry
  `pytestmark = pytest.mark.integration` + the `TEST_DATABASE_URL` guardrail; the
  hybrid sandbox+DB test carries the marker + BOTH the `TEST_DATABASE_URL` guardrail
  AND a module-level skip on `MESH_BASE_URL` (new category — document in
  arch_testing.md at step 8). No `ci.yml`/`Makefile` changes needed (marker-based
  discovery).

## Steps

1. **`app/services/delivery/mesh_constants.py`** (new). The three constants above,
   commented (shorter-than-email rationale; bounded-handshake rationale).

2. **`app/services/delivery/mesh_payload.py`** (new) + **`tests/test_mesh_payload.py`**.
   Frozen dataclass `MeshPayload(payload_bytes: bytes, content_type: str)`;
   `MeshPayloadBuilder` Protocol with `build(*, pdf_bytes: bytes) -> MeshPayload`;
   `RawPdfPayloadBuilder` (bytes unchanged, `application/pdf`). Docstring notes
   provisional status + builder/workflow-ID coupling note for the GP Connect ticket.

3. **Repository changes** (+ tests):
   - `delivery_repository.py`: `create_job` gains keyword-only `is_fallback: bool = False`,
     written in the INSERT. Existing callers unaffected.
   - `submission_repository.py`: new `get_delivery_metadata(submission_id) -> dict`
     (condition_label, submitted_at only); not-found raises per the repo's existing pattern.
   - `mesh_repository.py`: new `list_orphaned_fallbacks() -> list[dict]` —
     `fallback_triggered` rows LEFT JOIN `delivery_jobs` on submission_id where NULL;
     returns id + submission_id.
   - Tests: extend `tests/test_repositories.py` (is_fallback TRUE persists / defaults
     FALSE; metadata method incl. not-found) and `tests/integration/test_mesh_repository.py`
     (orphan query finds gap, ignores satisfied fallbacks and other statuses).

4. **`app/services/delivery/mesh_worker.py`** (new) + **`tests/test_mesh_worker.py`**.
   Loop: sweep, then claim one row; process: read attachment
   (`attachment_repo.get_attachment`), `payload_builder.build`, `send_message(
   recipient_mailbox_id=row, payload_bytes, workflow_id=config, mex_localid=str(...),
   content_type)`; 202 -> `mark_sent`; `MeshTransientError` -> `mark_failed` with
   `_compute_backoff(attempt_count)`; if returned attempt_count >= MAX -> fallback;
   `MeshTerminalError` -> fallback immediately. Fallback = `mark_fallback_triggered`
   THEN `create_job(is_fallback=True)` with metadata from get_delivery_email +
   get_delivery_metadata (ordering invariant). Also `_handshake_with_retry(client,
   delays, sleep_fn=time.sleep)` here for testability. Unit tests: success; backoff
   values per attempt; transient exhaustion -> fallback; terminal -> fallback;
   call-order assertion (mark_fallback_triggered before create_job); fallback
   metadata sourcing; sweep recovery + ERROR log; empty queue sleeps; handshake
   transient-retry-then-abort / terminal-immediate-abort / success-after-retry.
   While here: defensive check (Open Item 5) that nothing in delivery path or
   webhook router reads is_fallback — report result.

5. **`mesh_worker_main.py`** (new). Mirrors pdf_worker_main: requires DATABASE_URL,
   MESH_WORKER_POLL_INTERVAL_SECONDS (positive int; NEW env var — Phase 5 checklist),
   MESH_BASE_URL, MESH_MAILBOX_ID, MESH_MAILBOX_PASSWORD, MESH_SHARED_KEY,
   MESH_CA_CERT_PATH, MESH_CLIENT_CERT_PATH, MESH_CLIENT_KEY_PATH, MESH_WORKFLOW_ID,
   MESH_RECIPIENT_MAILBOX_ID is NOT needed here (it lives on each mesh_jobs row).
   os.path.exists fail-fast on the three cert paths. init_telemetry("mesh-dispatcher")
   + Sentry tag. Construct MeshClient + RawPdfPayloadBuilder + repos, run
   _handshake_with_retry, then run_worker.

6. **`Dockerfile`**: single line — `COPY mesh_worker_main.py ./` beside the existing
   worker COPY lines (currently lines 42-43). Advise user in chat; no artifact needed.

7. **Integration tests** (two new files):
   - `tests/integration/test_mesh_worker_db.py` — marker + TEST_DATABASE_URL guard;
     client mocked. Terminal failure -> delivery_jobs row with is_fallback=TRUE and
     correct denormalised fields; manufactured orphan recovered by one sweep pass.
   - `tests/integration/test_mesh_worker_sandbox.py` — HYBRID: marker +
     TEST_DATABASE_URL guard + MESH_BASE_URL module skip. Real mesh_jobs row, one
     dispatch tick against sandbox: row -> sent, message_id stored verbatim 32-hex.

8. **Docs wrap-up** (after green): arch_submission.md (ordering invariant, sweep,
   metadata-access deviation), arch_testing.md (hybrid category), file_structure.md,
   mesh_integration_plan.md modified-files delta (mesh_repository.py), deployment
   checklist note (new env var, Railway service for dispatcher, delivery worker must
   stay deployed). Prompt user re test markers per the Test Maintenance Obligation.

## Out of scope (restated)

No delivery_worker.py / delivery_service.py / webhook router / frontend changes.
No Phase 4 code; the `failed` status setter remains a Phase 4 method.
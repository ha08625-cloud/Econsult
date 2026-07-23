# Testing Architecture

**LLM INSTRUCTIONS:** This document describes the testing strategy, database separation rules, test conventions, and the Test Index (the single source of truth for what each test file covers). Read this before adding or modifying tests. Read the test files directly for individual test details and assertions.

**MAINTENANCE RULE:** When a test file is added, removed, or its scope materially changes, update its row in the Test Index below. Do not describe test files in any other document — `file_structure.md` records directory layout only and points here.

---

## Scope

Testing conventions, database separation, test categories, the Test Index, and the obligations that come with each. Covers how to run tests, when each category applies, and what must be done when the schema changes.

---

## Two-Database Rule

The system has two Postgres databases on Railway:

| Database | Purpose | Variable |
|---|---|---|
| Production | Live application data | `DATABASE_URL` |
| Test | Integration tests only (`test-practice`) | `TEST_DATABASE_URL` |

These must never be the same URL locally. All integration test modules enforce this with a hard guardrail at the top of the file: if `TEST_DATABASE_URL` is not set, the entire module is skipped. This guardrail must never be removed, even during development.

**CI exception:** In GitHub Actions, `DATABASE_URL` and `TEST_DATABASE_URL` intentionally point at the same ephemeral Postgres container. This is safe because the container is created fresh for each run, contains no real data, and is destroyed when the job completes. The two-database rule exists to protect production data locally — it does not apply to a throwaway CI container.

The test database is provisioned separately on Railway and seeded with a practice record:
- `practice_id`: `test-practice`
- `name`: `Test Practice`
- `email`: `test@example.com`

Both URLs live in `.env`. `.env` is never committed to version control.

---

## Test Categories

### Unit tests
Tests that do not require a database connection. Covers two suites that run together under `make test`:

**Python unit tests** — routers, validation, serialisation, sanitisation, engine logic, and worker loop. Use stubs and in-memory state.
- Files: any `test_*.py` file in `tests/` that does NOT carry `pytestmark = pytest.mark.integration`
- Runner: pytest via `pytest tests/ -m "not integration"`

**Shared fixtures (`tests/conftest.py`)** — contains a single `autouse=True` fixture that resets the SlowAPI in-memory rate limit storage before and after every test. This prevents the module-level `Limiter` instance from leaking counter state across test boundaries. Any test that fires multiple requests to a rate-limited endpoint would cause spurious 429 failures in subsequent tests without this reset. The fixture is always active; no opt-in is required.

**Frontend component tests** — screen component rendering and interaction behaviour.
- Files: `*.test.tsx` in `frontend/src/screens/` and `frontend/admin-ui/src/screens/`. Pure helper/util modules are tested by `*.test.ts` files colocated with the module (e.g. `frontend/src/helpers.test.ts`, covering the quantity unit-toggle helpers). Vitest discovers any `*.test.ts(x)` under `frontend/`, not only screen tests.
- Runner: Vitest (jsdom environment, configured in `frontend/vitest.config.ts`)
- **Naming rule:** the filename must use the dot form (`Name.test.tsx`), not an underscore (`Name_test.tsx`). Vitest's default discovery pattern only matches the dot form; an underscore-named file is silently never run.

**Frontend TypeScript type check** — full type-checking pass across the frontend codebase.
- Runner: `tsc --noEmit` via the project `tsconfig.json`
- Runs in CI only (not via `make test`) — see design decision below.
- Catches type errors that Vitest misses because Vitest transpiles TypeScript without checking types.

**Run Python unit tests and Vitest together with:**
```
make test
```

The `tsc --noEmit` type check is not included in `make test` — it runs in CI only. No database environment variables required. Vitest is invoked via `npx vitest run` from the `frontend/` directory.

---

### Integration tests
Tests that exercise the full request pipeline or repository layer against a live Postgres database. Identified by the module-level marker:

```python
pytestmark = pytest.mark.integration
```

This line must appear in every integration test file, after the `TEST_DATABASE_URL` guardrail block. pytest discovers all integration tests automatically via `-m integration`. No changes to `Makefile` or `ci.yml` are needed when adding a new integration test file — only the marker is required.

The marker is registered in `pytest.ini` at the project root.

**Integration status is conferred by the marker, not by directory.** All Python integration test files live flat in `tests/` alongside the unit tests. There is no `tests/integration/` folder.

### Guardrail variants (MESH sandbox tests)

Three integration-test shapes exist; every integration file is exactly one of them:

1. **Standard (DB-only)** — the default. `TEST_DATABASE_URL` guardrail first, then the marker. Examples: `test_repositories.py`, `test_mesh_repository.py`, `test_mesh_worker_db.py`.
2. **DB-free sandbox** — talks to the local MESH sandbox over HTTPS, never touches Postgres. Carries the marker and a module-level skip on `MESH_BASE_URL`, but deliberately OMITS the `TEST_DATABASE_URL` guardrail. The remaining MESH env vars are read with direct `os.environ[...]` subscripts so a half-configured `.env.sandbox` fails loudly (a `KeyError`, not a skip). Sole example: `test_mesh_client_integration.py`.
3. **Hybrid (DB + sandbox)** — needs both Postgres and the sandbox. Carries the marker, the `TEST_DATABASE_URL` guardrail (first, before any app imports), AND the `MESH_BASE_URL` module-level skip; remaining MESH env vars use direct subscripts as in shape 2. Sole example: `test_mesh_worker_sandbox.py` (the Phase 3 dispatch-tick test).

In CI, shapes 2 and 3 self-skip because `MESH_BASE_URL` is unset there; they run locally with `make sandbox-up` and a populated `.env.sandbox` (which must include `MESH_WORKFLOW_ID` from Phase 3 onwards).

**Run all integration tests with:**
```
make test-integration
```

---

### All tests
```
make test-all
```

Runs Python unit tests, then frontend Vitest, then Python integration tests, in that order. Stops on first failure.

---

## Test Index

Single source of truth for what each test file covers. One row per file; details, assertions, and mocking strategy live in the file's own header docstring.

### Python unit tests (`tests/`)

Runner: `pytest tests/ -m "not integration"`. None of these touch a database or the network.

| File | Subject under test | Scope |
|---|---|---|
| `test_settings.py` | `app/core/settings.py` | Env requiredness rules, `delivery_mode` selection (complete/partial Mailgun, SMTP, precedence), conditional signing-key rule, `MESH_DELIVERY` exact-value rejection, error message quality. Exercises the real env-sourcing path via monkeypatch from a fully cleared environment. |
| `test_wiring.py` | `app/core/wiring.py` + `dependencies.py` | Dynamically enumerates every `get_*` getter and pins the getter-to-`AppContainer`-field contract; also pins container frozen-ness and `unpack_container`. |
| `test_admin_context.py` | `app/core/admin_context.py` | Subprocess import-surface guard: importing `admin_context` must not pull in the repository/service/wiring closure. |
| `test_email_mode.py` | `app/core/email_mode.py` | Pure predicates for complete/partial Mailgun configuration, called directly with plain arguments (no env plumbing — that is `test_settings.py`'s concern). |
| `test_upload_constants.py` | `app/core/upload_constants.py` | JSON-backed constants load with the expected names, types, and values. |
| `test_availability_service.py` | `app/services/admin/availability_service.py` | `MAX_AVAILABILITY_MESSAGE_LENGTH` checks on `validate_availability_config` and `validate_override`; `evaluate_availability`'s fallback to the weekly schedule on malformed `custom_hours` exception rows (three malformed shapes × weekly-open/weekly-closed outcomes, plus a `caplog` warning assertion). Deliberately excludes day/time validation and well-formed evaluation paths, covered indirectly via `test_admin_availability_router.py`. |
| `test_form_logic.py` | `engine/form_logic` | Number answer validation and normalisation tiers; answer provenance (`apply_patient_answers` deriving `source`, idempotency, `normalise_encoder_provenance` promotion and selectivity). |
| `test_projection.py` | `engine/projection` | Locks `EXPLICIT_SOURCES` membership and the `None`-projection of every excluded source (raw `encoder`, `unanswered`). |
| `test_ruleset.py` | `engine/ruleset` | Fail-fast startup validation of Number-question and `answer_type` configuration (quantity/unit-system rules); `load_ruleset` per-path caching. |
| `test_serialisation.py` | `engine/serialisation` | Number-field passthrough in the client view (`decimal_places`/min/max/warning text), omission for other types, `current_value` as stored string; `change_count` surfaces only in `AuditOutput`. |
| `test_unit_conversion.py` | `engine/unit_conversion` | Exactness of `imperial_weight_to_kg` and the whole/non-negative component guards (raises `ValueError`; domain translation happens in `form_logic`). |
| `test_request_validation.py` | `request_validation.validate_patient_details` | All validation paths: DOB numeric checks and calendar assembly, future-date rejection, postcode format, submitter conditionals, gender/`nhs_number`/`preferred_name`. |
| `test_sanitise_signposting.py` | `practice_repository.sanitise_signposting_html` | nh3-based HTML sanitisation accept/reject cases. Requires `nh3` installed. |
| `test_practice_endpoint.py` | `public_router` `GET /practice` | Endpoint behaviour with a stub practice repo on a bare FastAPI app. |
| `test_image_sanitizer.py` | `utils/image_sanitizer` | JPEG passthrough, PNG-to-JPEG normalisation, EXIF stripping, truncated/garbage input rejection, standard/high tier encodes, no upscaling within bounds. |
| `test_pdf_generation.py` | `utils/pdf_formatter.generate_pdf` | PDF output structure assertions. Home of the shared `MINIMAL_JPEG` fixture (see Design Decisions). |
| `test_delivery_service.py` | `delivery_service` | Static email body format; SMTP and Mailgun HTTP implementations; configuration validation, provider message-ID extraction, PDF attachment handling, error cases. |
| `test_delivery_worker.py` | `delivery_worker` loop | One-job-per-iteration processing with all dependencies faked and `time.sleep` patched; provider-ID branching (`str` result marks accepted, `None` follows the legacy SMTP path). |
| `test_pdf_worker.py` | `pdf_worker` loop | Successful job ordering (attachment UPSERT, downstream enqueue, mark done), photo-count mismatch failure, UPSERT idempotency. Mocked dependencies, patched sleep. |
| `test_downstream_enqueuer.py` | `DownstreamEnqueuer` / `DeliveryEnqueuer` | Pure-forwarder coverage with MagicMock repositories (email path). Underlying repositories are integration-tested in `test_pipeline_repositories.py`. |
| `test_mesh_enqueuer.py` | `MeshEnqueuer` | Pure-forwarder coverage with a mocked `MeshRepository` (MESH path). Repository itself is integration-tested in `test_mesh_repository.py`. |
| `test_mesh_client.py` | `mesh` client library | `MeshClient` with `requests` mocked; a golden HMAC auth-header value is pinned as a literal so any header-construction refactor fails loudly. |
| `test_mesh_payload.py` | `MeshPayloadBuilder` seam / `RawPdfPayloadBuilder` | Pure-function payload construction coverage. |
| `test_mesh_worker.py` | `mesh_worker` processing helpers | Dispatcher helpers with mocked client and repositories, real `RawPdfPayloadBuilder`, no loop execution, no real sleeping. DB and sandbox coverage live in the integration files below. |

### Admin sub-router unit tests (`tests/routers/`)

Runner: same as above. All use `make_test_app`, `dummy_conn`, and the stubs from `tests/helpers/admin_test_helpers.py` (see Admin Unit Test Infrastructure below), authenticating via `TEST_SESSION_COOKIE`.

| File | Subject under test | Scope |
|---|---|---|
| `test_admin_auth_router.py` | `admin_context` + `admin_auth_router` | Session-cookie auth behaviour; `POST /auth/login` (correct credentials, wrong password, lockout, no password set, missing fields); `POST /auth/verify` (OTP); `POST /auth/request-reset` (registered and unregistered emails); `POST /auth/set-password` (valid/expired/unknown token, weak password, token consumed on use); `POST /auth/logout`; SlowAPI rate limiting on all four unauthenticated auth endpoints. |
| `test_admin_availability_router.py` | `admin_availability_router` | GET/PUT availability config, POST/DELETE override, GET/PUT/DELETE per-date exceptions. |
| `test_admin_practice_router.py` | `admin_practice_router` | Conditions, practice settings, signposting (including HTML sanitisation logic), doctor list endpoints. |
| `test_admin_audit_router.py` | `admin_audit_router` | `GET /admin/audit-log`. |
| `test_admin_user_router.py` | `admin_user_router` | List, add, delete, resend-invitation for admin users, including email-delivery-failure reporting (`email_sent == False`) and rate limits. |

### Python integration tests (`tests/`, marker `-m integration`)

Runner: `make test-integration`. Shape refers to the Guardrail variants above.

| File | Shape | Subject under test | Scope |
|---|---|---|---|
| `test_form_routes.py` | 1 | Full form-session pipeline | End-to-end happy path via FastAPI TestClient, delivery failure behaviour, availability fail-open, photo upload validation. Defines `MockDeliveryService` (see Design Decisions). |
| `test_public_routes.py` | 1 | Public (unauthenticated) endpoints | Full HTTP-to-database path via TestClient. Imports `main.py` directly, triggering `alembic_upgrade()` at import; uses `DATABASE_URL` rather than `TEST_DATABASE_URL` because it exercises the full app startup path. |
| `test_repositories.py` | 1 | `RuntimeStateRepository`, `PracticeRepository`, `SubmissionRepository`, `AttachmentRepository` | Repository-layer persistence; each test creates unique IDs and cleans up in a `finally` block. |
| `test_pipeline_repositories.py` | 1 | `PDFRepository`, `DeliveryRepository`, `PhotoRepository` | Direct exercise of `pdf_jobs`, `delivery_jobs`, `submission_photos`; `claim_next_pending` eligibility via backdated `next_retry_after`. No HTTP layer. |
| `test_webhook_router.py` | 1 | Mailgun webhook router | HMAC signature verification, timestamp staleness, replay protection, all status transitions (`delivered`, `failed`, `dropped`, informational). Builds a minimal app rather than importing `main.py` (see Design Decisions). |
| `test_mesh_repository.py` | 1 | `MeshRepository` | Every method against `mesh_jobs`: idempotent `create_job`, claim/retry-push, the `mark_*` transitions, `MeshJobNotFound`. Pure persistence — no MESH protocol or network. |
| `test_mesh_worker_db.py` | 1 | MESH dispatcher fallback + recovery sweep | Real repositories against real Postgres with a mocked `MeshClient`: terminal failure produces an `is_fallback=TRUE` `delivery_jobs` row with correct denormalised fields; a manufactured orphan is repaired idempotently by one sweep pass. |
| `test_pdf_worker_mesh_path.py` | 1 | PDF worker on the MESH downstream path | `pdf_worker._process_job` wired with `MeshEnqueuer` writes a `mesh_jobs` row (not `delivery_jobs`) while preserving the ordering invariant; re-processing is idempotent. No dispatcher runs. |
| `test_mesh_client_integration.py` | 2 | `MeshClient` against the local sandbox | mTLS + HMAC code path against the mesh-sandbox behind its nginx proxy. DB-free: the documented exception to the `TEST_DATABASE_URL` guardrail convention. Skips unless `MESH_BASE_URL` is set. |
| `test_mesh_worker_sandbox.py` | 3 | Full dispatch tick | Real `mesh_jobs` row, real `MeshClient`, real repositories, end to end against DB plus sandbox. Requires `MESH_WORKFLOW_ID` in `.env.sandbox`. |

### Frontend patient app tests (`frontend/src/`)

Runner: Vitest (jsdom). Screen tests live in `frontend/src/screens/`; module tests are colocated with the module. All mock `./api` (or `../api`) with `vi.mock` so no real HTTP calls are made.

| File | Subject under test | Scope |
|---|---|---|
| `App.test.tsx` | `App.tsx` | Condition-selection / free-text-preservation flow: drives SAFETY_WARNING through PATIENT_DETAILS, OUTCOME, SELECT_CONDITION to FREE_TEXT and back (ConditionCombobox mount-sync fix, `confirmedConditionId`, condition-change warning modal). Deliberately excludes EDIT, REVIEW, CONTACT, submission, photo upload, and error paths. |
| `helpers.test.ts` | `helpers.ts` | Quantity unit-toggle helpers: editable-answer seeding, shared-toggle seed, component-key maps, string-to-number payload conversion. Pure functions, no React. |
| `ConditionCombobox.test.tsx` | `ConditionCombobox.tsx` | Search and selection behaviour of the combobox in isolation. |
| `screens/SafetyWarningScreen.test.tsx` | `SafetyWarningScreen` | Warning-text rendering from fetch state, confirmation gating, practice-closed message and after-hours notice variants. |
| `screens/PatientDetailsScreen.test.tsx` | `PatientDetailsScreen` | Detail-field rendering and interaction driving the continue action. |
| `screens/OutcomeScreen.test.tsx` | `OutcomeScreen` | Outcome option rendering and selection behaviour. |
| `screens/SelectConditionScreen.test.tsx` | `SelectConditionScreen` | Condition list rendering, search, and selection. |
| `screens/FreeTextScreen.test.tsx` | `FreeTextScreen` | Free-text entry and the `initForm` call path (helpers mocked). |
| `screens/EditScreen.test.tsx` | `EditScreen` | Answer editing against `ClientStateView`, `updateForm` call path, photo tier handling. |
| `screens/ReviewScreen.test.tsx` | `ReviewScreen` | Review rendering of client state, safety messages, and photo attachments. |
| `screens/ContactScreen.test.tsx` | `ContactScreen` | Contact detail entry and the `finishForm` submission path. |
| `screens/DoneScreen.test.tsx` | `DoneScreen` | Confirmation rendering including icon accessibility (`aria-hidden`) and the practice-was-closed variant. |

### Frontend admin UI tests (`frontend/admin-ui/src/screens/`)

Runner: Vitest (jsdom). All mock `../api` with `vi.mock`; `AuthError` is kept real where `instanceof` checks matter.

| File | Subject under test | Scope |
|---|---|---|
| `LoginView.test.tsx` | `LoginView` | Step 1 rendering and behaviour (credential normalisation, advance to step 2, errors), forgot/set-up-password link, step 2 OTP rendering and behaviour, navigation between steps. |
| `EditorView.test.tsx` | `EditorView` | Tab orchestration with all child components mocked; unsaved-change signalling via the children's `onUnsavedChange` (stubs expose `triggerUnsaved`). |
| `SignpostingEditor.test.tsx` | `SignpostingEditor` | Editor behaviour using a hand-written Quill fake (Quill is imperative DOM and does not run in jsdom). |
| `AvailabilityEditor.test.tsx` | `AvailabilityEditor` | Initial load, schedule editing, override panel, exception panel. `window.confirm` (save with no days selected) is deliberately untested. |
| `PracticeSettingsTab.test.tsx` | `PracticeSettingsTab` | Shared load state; contact email display/edit/save; doctor list display, add, reorder, delete, save. |
| `AuditLogTab.test.tsx` | `AuditLogTab` | Audit log fetching and rendering via mocked `fetchAuditLog`; `AuthError` handling. |
| `UsersTab.test.tsx` | `UsersTab` | User list rendering, add, remove, resend invitation via mocked API functions; `AuthError` handling. |

### Known coverage gaps

Recorded so they are deliberate, not forgotten:

- `SetPasswordView` (admin UI) has no test file.
- `App.test.tsx` explicitly excludes the EDIT, REVIEW, CONTACT, submission, photo upload, and error paths at the App level (the individual screens are tested in isolation).
- `AvailabilityEditor`'s `window.confirm` branch is untested by design (requires mocking a browser global).
- The infinite `run_worker` loops (`delivery_worker`, `pdf_worker`, `mesh_worker`) are not executed by any test; their processing helpers are tested directly.

---

## Schema Migration Obligation

Current Alembic migrations:

- `0001_initial_schema.py` — creates the complete baseline schema.
- `0002_user_management_cascade.py` — adds `ON DELETE CASCADE` to `admin_sessions.user_id` FK and adds `admin_users.last_login` (nullable `TIMESTAMPTZ`).
- `0003_webhook_tracking.py` — adds `provider_message_id` and `provider_events` to `delivery_jobs`, extends the status check constraint, and creates the `webhook_tokens` replay protection table.
- `0004_password_auth.py` — adds password columns (`hashed_password`, `failed_password_attempts`, `password_locked_until`, `password_changed_at`) to `admin_users`; creates `admin_password_reset_tokens`.
- `0005_mesh_schema.py` — creates `mesh_jobs` (outbound MESH delivery queue); adds `delivery_jobs.is_fallback`.
- `0006_availability_exception_constraint.py` — adds CHECK constraints backstopping the app-layer time invariants on `practice_availability` (`open_time < close_time`) and `practice_availability_exceptions` (`exception_type` tied to time-column nullability and ordering).

See `file_structure.md` for the full per-migration detail; this list exists here only so the obligation below is self-contained. New schema changes should be added as further numbered migrations (`0007_...` etc.) rather than modifying existing ones, now that real data is involved.

When the schema changes, the test database on Railway must be updated to match. Because the test database is not deployed to automatically, run:

```
make migrate-test
```

If you forget, integration tests will fail against a stale schema.

---

## Admin Unit Test Infrastructure (`tests/helpers/admin_test_helpers.py`)

All admin sub-router unit tests share a common set of stubs and an app factory defined in `admin_test_helpers.py`. Understanding this infrastructure is necessary when writing new admin tests.

**`make_test_app`** builds a bare FastAPI app with the full admin router registered and `app.state` populated with stub dependencies. It registers the same exception handlers as `main.py`:
- `ConditionNotFound` → 404
- `APIError` → uses `exc.status_code` (not hardcoded 422 — this matters for user management errors which return 403, 404, and 409)
- `RateLimitError` → 429

The `with_rate_limiting=True` flag additionally wires `SlowAPIMiddleware` and the `RateLimitExceeded` handler. Pass it only in tests that specifically exercise slowapi counter behaviour.

**`dummy_conn`** is a context manager stub that replaces `app.core.db.get_conn` in unit tests. It yields a sentinel string so that `with get_conn(...) as conn:` blocks in routers succeed without opening a real Postgres connection. Stub repositories accept `conn=None` and ignore it entirely.

**Key stubs:**

`StubAuthRepo` — in-memory auth repo. Session lookup returns a valid context only for `"test-session-id"`. Also exposes the user management methods used by `admin_user_router`: `get_users_by_practice`, `get_user_by_id`, `insert_user`, `delete_user`. Tests that need to control user list contents should subclass or replace this stub.

`StubPracticeRepo` — in-memory practice repo. Includes `lock_practice(practice_id, conn)` which is a no-op in tests (the stub operates on in-memory state; no real lock is needed).

`StubAdminDeliveryService` — captures calls in two separate lists:
- `mfa_calls` — records `{"email": ..., "code": ...}` for each `send_mfa_code` call
- `invitation_calls` — records `{"email": ...}` for each `send_admin_invitation` call

When writing user management tests that need to simulate delivery failure, pass a custom delivery service subclass that raises `RuntimeError` from `send_admin_invitation` and assert that `response.json()["email_sent"] == False`.

`StubAuditRepo` — no-op audit repo. Records calls to `log_event` in `self.logged` so tests can assert the audit trail was written.

---

## Design Decisions

### Why not load .env automatically in tests?
The `TEST_DATABASE_URL` must be set explicitly as an environment variable rather than loaded automatically from `.env`. This is deliberate: it forces an opt-in decision when running integration tests, preventing accidental writes to the wrong database. The Makefile uses `include .env` / `export` to load it when you run `make test-integration`, which provides convenience without removing the guardrail.

### Why does the CI integration job assert TEST_DATABASE_URL before running pytest?
The per-module `pytest.skip()` guardrail is correct locally but produces a silent pass in CI if the variable is accidentally dropped — all integration tests skip with no failure signal. The explicit shell assertion in the CI integration job catches this at the environment check step, before pytest even runs, producing a clear error message. Both defences are kept: the guardrail protects local runs, the assertion protects CI.

### Why does MockDeliveryService exist?
Integration tests import `main.py` which triggers startup validation. To pass validation without real Mailgun credentials, `test_form_routes.py` sets stub Mailgun env vars (`MAILGUN_API_KEY`, `MAILGUN_DOMAIN`, `EMAIL_FROM`, `MAILGUN_SIGNING_KEY`, `ALLOWED_ADMIN_DOMAINS`) before the import. This means `MailgunHttpDeliveryService` is instantiated at startup, but the tests override it at the route level using `MockDeliveryService`. `MockDeliveryService` captures send calls in memory so tests can assert on delivery behaviour without making real network calls. It is defined in `test_form_routes.py` and is not shared — if other test files need delivery assertions in future, extract it to a shared `tests/fixtures.py`.

### Why does MockDeliveryService return a provider ID string?
`send_clinical_output` now returns `str | None`. `MockDeliveryService` returns a mock provider ID string by default so that integration tests exercise the Mailgun path (worker calls `mark_as_accepted`). Tests that need to exercise the SMTP legacy path should set `return_value = None` on the mock explicitly.

### Why does the CI unit job run tsc --noEmit separately from Vitest?
Vitest transpiles TypeScript using esbuild, which deliberately skips type checking for speed. This means Vitest tests can pass while genuine TypeScript type errors exist in the codebase — those errors only surface during the production build (`tsc -b && vite build`). Running `tsc --noEmit` as a distinct CI step catches type errors at the earliest possible point, before Vitest runs and well before any deployment build is attempted. It does not duplicate Vitest — it covers a gap Vitest cannot fill. It is not added to `make test` because `tsc` is slow relative to Vitest and adds friction to the local development loop; CI is the right enforcement point.

### Why cd frontend instead of a vitest script in package.json?
Vitest requires the working directory to be `frontend/` so it resolves `vitest.config.ts` correctly. The Makefile uses `cd frontend && npx vitest run` rather than adding a `test` script to `package.json` to keep the entry point for tests in one place (the Makefile) rather than split across two files.

### Why does test_delivery_worker.py patch attempt_delivery at delivery_worker rather than delivery_orchestration?
When `delivery_worker.py` imports `attempt_delivery` at the top of the file, Python binds the name in `delivery_worker`'s module namespace. Patching `delivery_orchestration.attempt_delivery` replaces the object in the source module but `delivery_worker` still holds the original reference. Patching `delivery_worker.attempt_delivery` intercepts all calls made by the worker. This is standard Python mock patching behaviour and is documented in the test file itself.

### MINIMAL_JPEG shared fixture
`MINIMAL_JPEG` is a module-level constant in `tests/test_pdf_generation.py`. Any test that needs a valid JPEG — for PDF generation tests or for multipart upload tests — should import it from there rather than duplicating the bytes. Do not define it in more than one place.

### Why does conftest.py reset the rate limiter before every test?
The SlowAPI `Limiter` instance in `app/core/rate_limit.py` is module-level and uses in-memory storage. Its counters persist across test boundaries within a single pytest session. Any test class that fires multiple requests to a rate-limited endpoint (such as `TestMFARateLimiting`) would contaminate later tests that simulate normal single-request traffic, causing spurious 429 failures. The `autouse=True` fixture in `conftest.py` resets the storage before and after every test, making each test independent of request history from previous tests.

### Why does TestMFARateLimiting use with_rate_limiting=True rather than the default make_test_app?
The standard `make_test_app` factory does not wire `SlowAPIMiddleware` or the `RateLimitExceeded` handler, keeping existing tests isolated from the rate limiting machinery. The `with_rate_limiting=True` flag mirrors the production `main.py` setup precisely: it attaches `app.state.limiter`, adds the middleware, and registers the 429 handler. This flag should only be passed in tests that specifically need to exercise the slowapi counter behaviour.

### Why are auth_service functions patched in TestMFARateLimiting?
The service-layer per-email cooldown in `auth_service.request_mfa_code` raises `RateLimitError` (HTTP 429) from the second request onward — before the slowapi IP counter reaches its limit. Without patching, the service-layer 429 would fire first and make it impossible to observe the slowapi counter reaching 5. Patching the service functions to no-ops isolates the two independent rate limiting mechanisms so each can be tested on its own terms.

### Why does user_service receive conn as an argument rather than opening its own connection?
`user_service.add_user` and `user_service.remove_user` both need to participate in a transaction opened by the router. The practice row lock, the user write, and the audit log write must all be atomic. Passing `conn` in as an argument keeps the service layer free of transaction management concerns and makes the boundary explicit: the router owns the transaction lifecycle, the service owns the business logic. `resend_invitation` performs no writes and therefore has no `conn` parameter.

### Why does test_webhook_router.py build its own FastAPI app rather than importing main.py?
The webhook router tests exercise only the webhook router in isolation. Importing `main.py` would trigger `alembic_upgrade()`, the full startup validation chain, and the delivery service instantiation — all of which require environment variables and a fully configured database. Building a minimal app with only the webhook router and the required `app.state` fields keeps the tests focused, faster, and free of startup-validation side effects.

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

This line must appear in every integration test file, after the `TEST_DATABASE_URL` guardrail block. pytest discovers all integration tests automatically via `-m integration`. No changes to `Makefile` or `tests.yml` are needed when adding a new integration test file — only the marker is required. (This does not apply to the ruleset-validation job below, which dispatches on changed paths rather than pytest markers.)

The marker is registered in `pytest.ini` at the project root.

### CI job layout (`.github/workflows/tests.yml`)

A `changes` job runs `dorny/paths-filter` unconditionally and produces two booleans that gate the three test jobs:

| Job | Gated on | Runs |
|---|---|---|
| `ruleset-validation` | `data/**` changed | `pytest tests/test_data_rulesets.py` and `pytest tests/test_synthetic_recombination.py` only — no database, no ruff, no frontend |
| `unit` | any non-doc, non-`data/**` change | ruff, `pytest tests/ -m "not integration"`, `tsc --noEmit`, Vitest |
| `integration` | same filter as `unit` | Postgres-backed `pytest tests/ -m integration` |

The filters are independent booleans, not an if/else, so a PR touching both `data/**` and `.py` files runs all three jobs. A PR touching only `data/**` runs `ruleset-validation` alone; a doc-only PR runs none of them. GitHub treats a job skipped by an `if:` condition as a passing required status check, so this is safe to depend on in branch protection — see the comment at the top of `.github/workflows/tests.yml`. When adding a fourth job, follow this pattern: add or reuse a `paths-filter` output, gate the job on it via `needs: changes` + `if:`, and keep the job itself narrowly scoped to what that path actually needs.

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
| `test_db.py` | `app/core/db.py` | Connection parameters and transaction lifecycle with `psycopg2.connect` monkeypatched and a stub connection: every timeout kwarg, both server-side timeouts in the `options` string, per-call overrides (the `deletion_job.py` path), keyword-only enforcement, and the error-masking guards — a failing `rollback()` or `close()` must not replace the original exception. Also asserts the full kwarg set parses as real libpq parameters via `make_dsn`, which catches a `tcp_user_timeout` unsupported by the bundled libpq without needing a server. Enforcement itself is `test_db_integration.py`. |
| `test_settings.py` | `app/core/settings.py` | Env requiredness rules, `delivery_mode` selection (complete/partial Mailgun, SMTP, precedence), conditional signing-key rule, `MESH_DELIVERY` exact-value rejection, error message quality. Exercises the real env-sourcing path via monkeypatch from a fully cleared environment. |
| `test_wiring.py` | `app/core/wiring.py` + `dependencies.py`; also `quantity_kind` registry parity | Dynamically enumerates every `get_*` getter and pins the getter-to-`AppContainer`-field contract; also pins container frozen-ness and `unpack_container`. Separately, asserts `ruleset.QUANTITY_KINDS`, `form_logic._NON_CANONICAL_CONVERTERS`, and `pdf_formatter._QUANTITY_FORMATTERS` agree on the same set of kinds, and that each kind's canonical system maps to exactly one component key. This cross-module check lives here rather than in `test_ruleset.py` or `test_pdf_formatter.py` because it is about agreement between layers, not the behaviour of any one of them. |
| `test_admin_context.py` | `app/core/admin_context.py` | Subprocess import-surface guard: importing `admin_context` must not pull in the repository/service/wiring closure. |
| `test_email_mode.py` | `app/core/email_mode.py` | Pure predicates for complete/partial Mailgun configuration, called directly with plain arguments (no env plumbing — that is `test_settings.py`'s concern). |
| `test_upload_constants.py` | `app/core/upload_constants.py` | JSON-backed constants load with the expected names, types, and values. |
| `test_http_utils.py` | `app/utils/http_utils.py` | Table-driven coverage of `extract_ip`'s right-to-left, globally-routable-only `X-Forwarded-For` trust walk: spoofed/private leftmost entries ignored, `x-real-ip` and `client_host` fallbacks, malformed entries, no-headers and nothing-determinable cases. |
| `test_form_logic.py` | `engine/form_logic` | Number answer validation and normalisation tiers; answer provenance (`apply_patient_answers` deriving `source`, idempotency, `normalise_encoder_provenance` promotion and selectivity). |
| `test_projection.py` | `engine/projection` | Locks `EXPLICIT_SOURCES` membership and the `None`-projection of every excluded source (raw `encoder`, `unanswered`). |
| `test_ruleset.py` | `engine/ruleset` | Fail-fast startup validation of Number-question and `answer_type` configuration (quantity/unit-system rules); `load_ruleset` per-path caching. Also `pdf_label` validation: non-empty string, rejected on text questions, unique within the ruleset. All fixtures are synthetic, built in-test — it validates the *rules*, not the committed data. |
| `test_data_rulesets.py` | The real `data/` tree | Loads every committed ruleset via `ConditionRegistry` and runs `validate_rulesets` on it — the same two calls `build_container` makes at `app/core/wiring.py:189`, before any repository exists, so it reproduces the startup contract with no database. Where `test_ruleset.py` validates the schema rules against synthetic fixtures, this file validates the real committed JSON against those rules. Also asserts the registry's discovered-condition count matches the on-disk `*.json` count, and that condition ids pinned by other tests by name (currently `numeric_capability_demo`, hardcoded in `tests/test_form_routes.py`) still exist. It carries no `integration` marker, so it runs in `make test` and in CI's `unit` job like any other unit test — but it is also the **sole** gate on a rulesets-only PR (see CI job layout below), since `test_form_routes.py` skips itself without `TEST_DATABASE_URL`. |
| `test_synthetic_recombination.py` | `scripts/synthetic_data/` (offline dataset generator) | Normalisation as the single key definition; cluster-aware 70/15/15 splitting and its stability under library growth; manifest validation and deduplication; the empty-`(library, split)`-cell guard; label-first recombination invariants (a positive fragment cannot reach a non-`true` example, exactly two fragments per example, split-restricted pools); byte-identical output for a given seed, pinned as golden label counts rather than a statistical tolerance; the JSONL schema and stats sidecar; and the three lint reports. **Mostly synthetic fixtures built in-test — but `test_no_filler_fragment_contains_fever_language` reads the real `data/synthetic/` tree**, since its whole purpose is to fail when a filler library acquires fever language, which no fixture can catch. That is why this file is also run by the `ruleset-validation` CI job: a `data/`-only PR skips the `unit` job, so the guard would otherwise never run on the edit it was written for. |
| `test_encoder_training_dataset.py` | `scripts/encoder_training/dataset.py` (offline training tooling) | Reading a generated split plus its stats sidecar: class indices, and the masked-vs-null distinction that only a hand-written fixture can cover (with one signal the generator never emits a missing key). Resolving the decisive fragment from `fragment_type` rather than library names, so a filler library cannot be inferred from its name; clustered `[c01]` siblings sharing one resampling unit. The sidecar contract as a set of hard errors: no fragment-provenance block, no fold configuration, an absent sidecar. Fold loading cross-checks — generator version and fold configuration agreement, and fragment- *and* cluster-level disjointness between every pair of splits. Also the `app/` import guard: nothing under `app/` may import either offline package (`scripts.synthetic_data` or `scripts.encoder_training`), enforced by AST walk. Fixtures are hand-built JSONL in `tests/fixtures/encoder_training/`; error cases are copies mutated in `tmp_path`. |
| `test_encoder_training_metrics.py` | `scripts/encoder_training/metrics.py`, `ruleset_hash.py` | Confusion-matrix orientation, per-class precision/recall/F1 with undefined quantities held as `None` rather than zero, macro-F1 skipping classes a slice never contained. The two load-bearing tests are about the *unit* of counting: effective n counts clusters not examples, and a cluster bootstrap over two ideas reports 0–1 where an example bootstrap over their 200 recombinations would report roughly ±0.07. Also bootstrap determinism and narrowing as clusters are added; exact two-sided McNemar against hand-computed p-values; the DD9 margin rule gating only the `true` class and never raising the `null → true` count as the margin rises. Finally the DD15 parity check: `scripts/encoder_training/ruleset_hash.py` and `app/services/engine/ruleset.py` must produce the same digest for the real `data/uti1.json`, which is the entire justification for duplicating that function rather than importing it. |
| `test_encoder_training_baselines.py` | `scripts/encoder_training/baselines.py`, `decision.py`, `report.py`, plus `dataset.load_folds` and `metrics.bootstrap_confusion_ci` | The baselines and everything downstream of them. Four tests are load-bearing: the fast confusion-matrix bootstrap returns *exactly* the interval the already-tested general bootstrap does (every error bar in the report comes from the fast path); the DD9 margin never worsens the `null → true` rate against argmax; `FoldRun.build` qualifies example ids with their fold, without which pooling five folds would collapse `test-000000` into one example and McNemar would compare a model against itself; and negative control 1 trains on permuted labels while being scored against the truth — asserted exactly, with a spy baseline, rather than statistically. Also directory-level fold loading (a file whose name lies about its fold, a `--folds` mismatch, a cluster held out twice), and the report writer end to end: effective n beside every example count, both confusion matrices present, the DD7 per-fragment table sorted worst-first, controls excluded from paired comparisons, and the markdown rendered from the JSON. Task 6 added four more to the report writer: the DD7 error-concentration statistic (how many fragments carry half the errors, against the even-spread reference point that makes the number readable); that the markdown lays out the ticket's model-or-libraries question and explicitly declines to answer it; that `arch_training.md` sections 9 and 10 are reproduced in the report *in full* rather than cited, since the report is read standalone; and a drift guard asserting the report's hard-coded per-library cluster table against the real `data/synthetic/` libraries -- the report must not re-read those libraries at render time, so a test is what stops the constant going stale. **The scikit-learn tests skip themselves** via `pytest.importorskip` — `requirements-ml.txt` is deliberately not installed in CI, which is why the sklearn imports sit inside the `fit` bodies rather than at module scope. |
| `test_encoder_training_arm_a.py` | `scripts/encoder_training/embed.py`, `model.py`, `train.py`, plus the CLI's import surface | Arm A. **The load-bearing tests are the ones that need no ML at all**, because Arm A's worst failure is silent: a stale embedding cache serves last month's vectors and produces a report full of plausible numbers with no warning anywhere. So the DD14 cache key is pinned field by field -- pooling mode, `max_seq_len`, revision, model name, signal, fold, split, generator version, dataset seed, and a digest of the example texts must each change the filename -- and the metadata sidecar is checked against the field list that makes a set of weights identifiable later. Also: the sidecar round-tripping back into an embedding spec, `CUBLAS_WORKSPACE_CONFIG` being set before torch could read it, JSON-not-pickle head artefacts, and that the CLI imports and parses with no torch installed. **The torch tests skip themselves** (`requirements-ml.txt` is not installed in CI) and cover the two quiet numerical failures: `masked_cross_entropy` on an all-masked batch returning a graph-connected zero rather than the NaN `F.cross_entropy` gives, which would destroy every weight on the next step; and mask-weighted mean pooling, so an embedding does not depend on the longest sentence in its batch. The arm runs end to end against stub encoders and a locally-built tiny BERT -- **no model download, ever** -- with one stub emitting linearly separable features so a break anywhere in embed -> loss -> step -> epoch selection -> margin selection -> scoring fails here rather than looking like a disappointing number on real data. |
| `test_encoder_training_arm_b.py` | `scripts/encoder_training/train.py` (fine-tune path), `smoke_cuda.py`, plus the CLI's `finetune` surface | Arm B. **The stdlib tests carry the load again**, and they are about honesty rather than arithmetic: the four validation-guided decisions task 5 caps are asserted to be four and to reach both the metadata sidecar and the report header, because how much the pooled result flatters itself depends on how many quantities were tuned that way and no reader can infer that from a hyperparameter list; the config is asserted to record that nothing was traded for memory (no checkpointing, no 8-bit optimiser, no LoRA, no accumulation); the head artefact is asserted to name the uncommitted `.pt` it is meaningless without, since for Arm B the JSON head is *not* the model; and the two arms are asserted to write to different directories, because both emit `metadata.json` and a shared one would have Arm B overwrite the Arm A result it is compared against. Also the warmup-then-decay schedule as pure arithmetic, and the `smoke_cuda` report calling out a Blackwell card on a pre-12.8 wheel by name. **The torch tests skip themselves**; the one that matters most is `test_each_fold_starts_from_pretrained_weights` -- reusing one encoder across folds would start each fold from a model already fine-tuned on the previous fold's training clusters, which are this fold's validation and test clusters, and every dataset-level disjointness check would still pass. The rest run the loop end to end on a locally-built tiny BERT (**no model download, ever**): the loss falls, the best epoch is restored, test is scored once, weights round-trip through `torch.save`, gradient checkpointing is refused, and the control permutes training labels only. |
| `test_serialisation.py` | `engine/serialisation` | Number-field passthrough in the client view (`decimal_places`/min/max/warning text), omission for other types, `current_value` as stored string; `change_count` surfaces only in `AuditOutput`. Quantity coverage: toggle fields on the client view, `current_value` as `{system, components}` with string components for both systems, null-but-present shape when unanswered, the `quantity_answers` sidecar on `ClinicalOutput`, and `from_dict` round-tripping the sidecar's four keys (`quantity_kind`, `raw_components`, `unit_system`, `decimal_places`). `pdf_labels` coverage: collected from authored labels only, empty when none authored, and round-tripped through `from_dict` (with the legacy-record case asserting an empty dict). |
| `test_unit_conversion.py` | `engine/unit_conversion` | Exactness of `imperial_weight_to_kg` and the whole/non-negative component guards (raises `ValueError`; domain translation happens in `form_logic`). |
| `test_request_validation.py` | `request_validation.validate_patient_details` | All validation paths: DOB numeric checks and calendar assembly, future-date rejection, postcode format, submitter conditionals, gender/`nhs_number`/`preferred_name`. |
| `test_body_capture.py` | `app/core/body_capture.py` | `read_json_body` on a router without `route_class=BodyCapturingRoute` raises the named `BodyNotCaptured` error, not a bare `AttributeError`. On a `BodyCapturingRoute` router: valid JSON round-trips through a plain `def` handler, and malformed JSON raises `INVALID_PAYLOAD` (422) via the existing envelope. |
| `test_sanitise_signposting.py` | `practice_repository.sanitise_signposting_html` | nh3-based HTML sanitisation accept/reject cases. Requires `nh3` installed. |
| `test_practice_endpoint.py` | `public_router` `GET /practice` | Endpoint behaviour with a stub practice repo on a bare FastAPI app. |
| `test_image_sanitizer.py` | `utils/image_sanitizer` | JPEG passthrough, PNG-to-JPEG normalisation, EXIF stripping, truncated/garbage input rejection, standard/high tier encodes, no upscaling within bounds. |
| `test_pdf_formatter.py` | `utils/pdf_formatter.generate_pdf` | PDF output structure assertions. Home of the shared `MINIMAL_JPEG` fixture (see Design Decisions). Quantity coverage: imperial renders stones/pounds with a parenthetical kg conversion, zero-`decimal_places` rounding, metric renders the typed kilograms verbatim, formatter dispatch on `quantity_kind`, and a missing `quantity_kind` in a persisted sidecar entry defaulting to `"weight"`. This file was renamed from `test_pdf_generation.py`; if any import still references the old module path, that is a bug, not a stale doc. CLINICAL SUMMARY coverage: block renders with labels and disappears without them, adds no content when unlabelled, a labelled quantity answer keeps its units, and the ANSWERS section stays complete when only some questions are labelled. |
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
| `test_db_integration.py` | 1 | `app/core/db.py` timeouts as the server applies them | `SHOW statement_timeout` / `SHOW idle_in_transaction_session_timeout` reflect the settings, an override is not sticky across connections, `pg_sleep` past the timeout raises `QueryCanceled` (not a masked `InterfaceError`), and `connect_timeout` bounds an unroutable host. Separate from `test_db.py` because the guardrail and marker are module-scoped and would otherwise skip the unit tests too. |
| `test_form_routes.py` | 1 | Full form-session pipeline | End-to-end happy path via FastAPI TestClient, delivery failure behaviour, availability fail-open, photo upload validation. Defines `MockDeliveryService` (see Design Decisions). Hardcodes `NUMERIC_DEMO_CONDITION_ID = "numeric_capability_demo"` and depends on `data/numeric_capability_demo.json`'s `patient_weight_kg` answer key for its quantity boundary tests; that condition id's existence is now also asserted by `test_data_rulesets.py`, so a rulesets-only PR that deletes or renames it fails fast instead of merging green. |
| `test_public_routes.py` | 1 | Public (unauthenticated) endpoints | Full HTTP-to-database path via TestClient. Imports `main.py` directly, triggering `alembic_upgrade()` at import; uses `DATABASE_URL` rather than `TEST_DATABASE_URL` because it exercises the full app startup path. |
| `test_repositories.py` | 1 | `RuntimeStateRepository`, `PracticeRepository`, `SubmissionRepository`, `AttachmentRepository` | Repository-layer persistence; each test creates unique IDs and cleans up in a `finally` block. |
| `test_pipeline_repositories.py` | 1 | `PDFRepository`, `DeliveryRepository`, `PhotoRepository` | Direct exercise of `pdf_jobs`, `delivery_jobs`, `submission_photos`; `claim_next_pending` eligibility via backdated `next_retry_after`. No HTTP layer. |
| `test_webhook_router.py` | 1 | Mailgun webhook router | HMAC signature verification, timestamp staleness, replay protection, all status transitions (`delivered`, `failed`, `dropped`, informational). Builds a minimal app rather than importing `main.py` (see Design Decisions). |
| `test_mesh_repository.py` | 1 | `MeshRepository` | Every method against `mesh_jobs`: idempotent `create_job`, claim/retry-push, the `mark_*` transitions, `MeshJobNotFound`. Pure persistence — no MESH protocol or network. |
| `test_audit_repository.py` | 1 | `AuditRepository` | Direct DB coverage of `admin_audit_log`, complementing the mocked SQL-building checks in `tests/routers/test_admin_audit_router.py`. `log_event`: round-trips through `list_events` (including that `session_id` is never selected even though it was written), and confirms a caller-supplied `conn` is not committed independently — a rollback on the caller's connection discards the insert. `list_events`: cursor round-trip across multiple pages with no gap or duplicate; tuple-comparison pagination (`(occurred_at, id) < (...)`) breaking ties correctly when several rows share the exact same `occurred_at`; inclusive UTC-midnight `from_date`/`to_date` boundaries against rows placed exactly on and just outside the boundary instants; and the left-anchored `action_prefix` match (including that it does not match as a substring mid-string). Rows are inserted directly via SQL where a specific `occurred_at` is required, since `log_event` always stamps `NOW()`. |
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
| `screens/ReviewScreen.test.tsx` | `ReviewScreen` | Review rendering of client state, safety messages, and photo attachments. Quantity coverage: imperial and metric display formatting via `QUANTITY_DISPLAY_FORMATTERS[quantity_kind]`, and the unanswered ("Not answered") case. |
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

New schema changes should be added as further numbered migrations (`0004_...` etc.) rather than modifying existing ones, now that real data is involved.

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

`StubAuthRepo` — in-memory auth repo. Session lookup returns a valid context only for `TEST_SESSION_ID` (a well-formed UUID constant — `require_admin` rejects non-UUID cookie values before the repository is ever called). Also exposes the user management methods used by `admin_user_router`: `get_users_by_practice`, `get_user_by_id`, `insert_user`, `delete_user`. Tests that need to control user list contents should subclass or replace this stub.

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
`MINIMAL_JPEG` is a module-level constant in `tests/test_pdf_formatter.py` (renamed from `test_pdf_generation.py`). Any test that needs a valid JPEG — for PDF generation tests or for multipart upload tests — should import it from there rather than duplicating the bytes. Do not define it in more than one place. `test_form_routes.py` and `test_image_sanitizer.py` must import `MINIMAL_JPEG` from `tests.test_pdf_formatter`; an import from `tests.test_pdf_generation` will fail collection now that the module has been renamed.

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
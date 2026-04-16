# Testing Architecture

**LLM INSTRUCTIONS:** This document describes the testing strategy, database separation rules, and test conventions. Read this before adding or modifying tests. Read the test files directly for individual test details and assertions.

---

## Scope

Testing conventions, database separation, test categories, and the obligations that come with each. Covers how to run tests, when each category applies, and what must be done when the schema changes.

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
- Files: `*.test.tsx` in `frontend/src/screens/` and `frontend/admin-ui/src/screens/`
- Runner: Vitest (jsdom environment, configured in `frontend/vitest.config.ts`)

**Run both together with:**
```
make test
```

No database environment variables required. Vitest is invoked via `npx vitest run` from the `frontend/` directory.

---

### Integration tests
Tests that exercise the full request pipeline or repository layer against a live Postgres database. Identified by the module-level marker:

```python
pytestmark = pytest.mark.integration
```

This line must appear in every integration test file, after the `TEST_DATABASE_URL` guardrail block. pytest discovers all integration tests automatically via `-m integration`. No changes to `Makefile` or `ci.yml` are needed when adding a new integration test file — only the marker is required.

The marker is registered in `pytest.ini` at the project root.

Current integration test files:

**`tests/test_form_routes.py`** — full request pipeline via FastAPI TestClient. Covers: happy-path end-to-end flow, delivery failure behaviour, availability fail-open, photo upload validation.

**`tests/test_public_routes.py`** — public endpoint tests via FastAPI TestClient. Imports `main.py` directly, which triggers `alembic_upgrade()` at import time. Uses `DATABASE_URL` rather than `TEST_DATABASE_URL` (it tests the full app startup path).

**`tests/test_repositories.py`** — repository layer tests for `RuntimeStateRepository`, `PracticeRepository`, `SubmissionRepository`, and `AttachmentRepository`.

**`tests/test_pipeline_repositories.py`** — repository layer tests for `PDFRepository`, `DeliveryRepository`, and `PhotoRepository`. Exercises the `pdf_jobs`, `delivery_jobs`, and `submission_photos` tables.

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

## Schema Migration Obligation

With a single consolidated migration (`0001_initial_schema.py`), schema changes now mean updating that file directly (at prototype stage, while no real data exists). Once real data is in play, new Alembic migrations will be added as before.

When the schema changes, the test database on Railway must be updated to match. Because the test database is not deployed to automatically, run:

```
make migrate-test
```

If you forget, integration tests will fail against a stale schema.

---

## Design Decisions

### Why not load .env automatically in tests?
The `TEST_DATABASE_URL` must be set explicitly as an environment variable rather than loaded automatically from `.env`. This is deliberate: it forces an opt-in decision when running integration tests, preventing accidental writes to the wrong database. The Makefile uses `include .env` / `export` to load it when you run `make test-integration`, which provides convenience without removing the guardrail.

### Why does the CI integration job assert TEST_DATABASE_URL before running pytest?
The per-module `pytest.skip()` guardrail is correct locally but produces a silent pass in CI if the variable is accidentally dropped — all integration tests skip with no failure signal. The explicit shell assertion in the CI integration job catches this at the environment check step, before pytest even runs, producing a clear error message. Both defences are kept: the guardrail protects local runs, the assertion protects CI.

### Why does MockDeliveryService exist?
Integration tests must not require SMTP configuration. `MockDeliveryService` captures send calls in memory so tests can assert on delivery behaviour without network dependencies. It is defined in `test_form_routes.py` and is not shared — if other test files need delivery assertions in future, extract it to a shared `tests/fixtures.py`.

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